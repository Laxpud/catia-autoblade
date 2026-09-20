"""FreeCAD 双制品校验与同文件系统逻辑事务。"""

import hashlib
import os
import re
import math
from pathlib import Path
import shutil
from uuid import uuid4
import zipfile

from ....core.backend import BackendError, BackendName


def recognizable_fcstd(path: Path) -> bool:
    """只识别完整 ZIP 中的 FreeCAD 文档；不把任意残缺文件当作失败快照。"""
    try:
        with zipfile.ZipFile(path) as archive:
            return "Document.xml" in archive.namelist() and archive.testzip() is None
    except OSError, zipfile.BadZipFile:
        return False


def validate_artifacts(staging: Path, result: dict, names: tuple[str, str]) -> None:
    """内核重开由 Child 验证，Host 独立核对文件、摘要、格式和重开结果。"""
    native, step = (staging / name for name in names)
    artifacts = result["artifacts"]
    for kind, path in (("native_model", native), ("step", step)):
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise BackendError(
                BackendName.FREECAD,
                "artifact_validation",
                f"Missing or invalid artifact: {path.name}",
            )
        if (
            artifacts.get(kind) != str(path)
            or artifacts.get(f"{kind}_sha256")
            != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise BackendError(
                BackendName.FREECAD,
                "artifact_validation",
                f"Artifact digest or path mismatch: {path.name}",
            )
    if not recognizable_fcstd(native):
        raise BackendError(
            BackendName.FREECAD,
            "artifact_validation",
            "Native model is not a recognizable FCStd.",
        )
    text = step.read_text(encoding="utf-8", errors="replace").upper()
    if not all(
        token in text
        for token in (
            "ISO-10303-21;",
            "AP242",
            "SI_UNIT(.MILLI.,.METRE.)",
            "END-ISO-10303-21;",
        )
    ):
        raise BackendError(
            BackendName.FREECAD,
            "artifact_validation",
            "STEP must contain AP242 geometry in mm.",
        )
    uncertainty = re.search(
        r"UNCERTAINTY_MEASURE_WITH_UNIT\(LENGTH_MEASURE\(([^)]+)\)", text
    )
    try:
        precision = float(uncertainty.group(1)) if uncertainty else math.nan
    except ValueError:
        precision = math.nan
    if not math.isclose(precision, 1e-7, rel_tol=1e-12, abs_tol=0):
        raise BackendError(
            BackendName.FREECAD,
            "artifact_validation",
            "STEP writer precision must be 1e-7 mm.",
        )
    reopen = result["measurements"].get("reopen", {})
    if not isinstance(reopen, dict):
        raise BackendError(
            BackendName.FREECAD, "artifact_validation", "Invalid CAD reopen validation."
        )
    if (
        reopen.get("fcstd_valid") is not True
        or reopen.get("fcstd_closed") is not True
        or reopen.get("fcstd_solids") != 1
        or reopen.get("step_valid") is not True
        or reopen.get("step_solids") != 1
        or reopen.get("embedded_request_sha256") != result["request_sha256"]
    ):
        raise BackendError(
            BackendName.FREECAD,
            "artifact_validation",
            "CAD reopen validation is incomplete or failed.",
        )


def publish(staging: Path, targets: tuple[Path, Path]) -> None:
    """先备份整个旧集合，再发布两个新文件；任何部分失败恢复原先状态。

    两次 rename 不是文件系统原子事务，外部读者应等待命令成功后再消费制品。
    若恢复也失败，必须保留 staging 内备份并报告位置，不能清理恢复证据。
    """
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for index, target in enumerate(targets):
            if target.exists() or target.is_symlink():
                if not target.is_file() or target.is_symlink():
                    raise ValueError(
                        f"Refusing to replace non-regular artifact: {target}"
                    )
                backup = staging / f"previous-{index}"
                os.replace(target, backup)
                backups[target] = backup
        for target in targets:
            os.replace(staging / target.name, target)
            published.append(target)
    except BaseException as error:
        failures = []
        for target in reversed(published):
            try:
                target.unlink()
            except OSError as cleanup:
                failures.append(str(cleanup))
        for target, backup in backups.items():
            try:
                os.replace(backup, target)
            except OSError as cleanup:
                failures.append(str(cleanup))
        if failures:
            raise BackendError(
                BackendName.FREECAD,
                "cleanup",
                f"Artifact rollback failed; recovery files retained at {staging}: {failures}",
            ) from error
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise BackendError(
            BackendName.FREECAD,
            "artifact_validation",
            f"Artifact publication failed and was rolled back: {error}",
        ) from error


def preserve_failed_model(staging: Path, native: Path) -> Path | None:
    """快照不覆盖历史结果；失败只保留原生文档，不发布 STEP。"""
    for candidate in (staging / "failed.FCStd", staging / native.name):
        if recognizable_fcstd(candidate):
            target = native.with_name(f"{native.stem}_failed_{uuid4().hex}.FCStd")
            # 只在独占创建成功后接管目标；复制中断时删除本次半文件，保留根因。
            destination = target.open("xb")
            try:
                with destination, candidate.open("rb") as source:
                    shutil.copyfileobj(source, destination)
            except BaseException as error:
                try:
                    target.unlink()
                except OSError as cleanup:
                    error.add_note(f"Partial failed-model cleanup failed: {cleanup}")
                raise
            return target
    return None
