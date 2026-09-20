"""FreeCAD Host 集成：闭合请求、受控进程、严格结果与双制品发布。"""

import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import warnings

from ....core.backend import BackendError, BackendName
from ....core.jobs import BladeBuildJob
from .artifacts import preserve_failed_model, publish, validate_artifacts
from .process import build_command, child_environment, run_process
from .protocol import (
    ProtocolError,
    CURVESWB_COMMIT,
    CURVESWB_VERSION,
    RESULT_SCHEMA,
    canonical_json,
    request_sha256,
    validate_curveswb_checkout,
)
from .request import build_request


def bundled_dependency() -> Path:
    """资源从已安装 package 定位，不依赖 checkout、网络或 Addon Manager。"""
    return Path(__file__).resolve().parents[3] / "_vendor" / "curveswb"


def validate_result(
    value: object, *, digest: str, dependency_digest: str, custom: bool
) -> dict:
    """拒绝未知 schema、伪成功、串任务结果和错误依赖身份。"""
    if not isinstance(value, dict) or value.get("schema_version") != RESULT_SCHEMA:
        raise ProtocolError("Unknown or missing FreeCAD result schema.")
    base = {
        "schema_version",
        "status",
        "freecad_version",
        "curveswb_commit",
        "curveswb_version",
        "dependency_status",
        "elapsed_seconds",
        "peak_rss_kib",
    }
    success = {
        "dependency_fingerprint_sha256",
        "request_sha256",
        "request_source",
        "measurements",
        "artifacts",
    }
    if not base.issubset(value) or not set(value).issubset(
        base | success | {"error", "error_code"}
    ):
        raise ProtocolError("FreeCAD result has missing or unknown fields.")
    if (
        value["curveswb_commit"] != CURVESWB_COMMIT
        or value["curveswb_version"] != CURVESWB_VERSION
    ):
        raise ProtocolError("Unexpected CurvesWB version identity.")
    for key in ("elapsed_seconds", "peak_rss_kib"):
        number = value[key]
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            or number < 0
        ):
            raise ProtocolError(f"Invalid FreeCAD result numeric field: {key}")
    if not isinstance(value["freecad_version"], list) or not all(
        isinstance(part, str) for part in value["freecad_version"]
    ):
        raise ProtocolError("FreeCAD version must be an array of strings.")
    if value["status"] not in {"passed", "failed"}:
        raise ProtocolError("Invalid FreeCAD result status.")
    if value["status"] == "failed":
        if (
            not isinstance(value.get("error"), str)
            or not value["error"].strip()
            or value.get("error_code")
            not in {
                "unavailable",
                "protocol",
                "geometry",
                "artifact_validation",
                "cleanup",
            }
        ):
            raise ProtocolError("Failed FreeCAD result has no error.")
        raise BackendError(
            BackendName.FREECAD,
            value.get("error_code", "geometry"),
            "FreeCAD modeling failed: " + value["error"].strip().splitlines()[-1],
            diagnostics=value["error"],
        )
    if not success.issubset(value) or "error" in value or "error_code" in value:
        raise ProtocolError("Successful FreeCAD result is incomplete.")
    if (
        value["request_sha256"] != digest
        or value["dependency_fingerprint_sha256"] != dependency_digest
    ):
        raise ProtocolError("FreeCAD request/dependency fingerprint mismatch.")
    if value["request_source"] != "closed_json":
        raise ProtocolError(
            "FreeCAD result source does not match the submitted request."
        )
    expected_status = "unverified_custom_dependency" if custom else "pinned"
    if value["dependency_status"] != expected_status:
        raise ProtocolError("FreeCAD dependency certification status mismatch.")
    if not isinstance(value["measurements"], dict) or not isinstance(
        value["artifacts"], dict
    ):
        raise ProtocolError("FreeCAD result measurements/artifacts must be objects.")
    try:
        version = tuple(int(part) for part in value["freecad_version"][:3])
    except ValueError, TypeError:
        raise ProtocolError("Invalid FreeCAD version.") from None
    if len(version) != 3 or version < (1, 1, 0):
        raise BackendError(
            BackendName.FREECAD, "unavailable", "FreeCAD >= 1.1 is required."
        )
    if version != (1, 1, 3):
        warnings.warn(
            f"Uncertified FreeCAD version: {version}; certified version is 1.1.3.",
            stacklevel=2,
        )
    return value


class FreeCADBackend:
    """一次 build 只拥有一个进程和目标文件系统中的一个暂存目录。"""

    def build(self, job: BladeBuildJob) -> None:
        """只有 Child 与 Host 均验证通过后才发布，失败不拼接新旧制品。"""
        dependency = (job.dependency_override or bundled_dependency()).resolve()
        custom = job.dependency_override is not None
        try:
            digests = validate_curveswb_checkout(dependency, custom=custom)
            request = build_request(
                job.input_plan,
                native_model=job.output_paths[0].name,
                step=job.output_paths[1].name,
            )
        except (ProtocolError, ValueError) as error:
            raise BackendError(BackendName.FREECAD, "protocol", str(error)) from error
        if custom:
            warnings.warn(
                "unverified_custom_dependency: custom CurvesWB source is not certified.",
                stacklevel=2,
            )
        dependency_digest = hashlib.sha256(canonical_json(digests).encode()).hexdigest()
        try:
            job.output_dir.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".autoblade-", dir=job.output_dir))
        except OSError as error:
            raise BackendError(
                BackendName.FREECAD,
                "artifact_validation",
                f"Cannot create artifact staging: {error}",
            ) from error
        retain = False
        diagnostics = ""
        try:
            (staging / "request.json").write_text(
                canonical_json(request), encoding="utf-8"
            )
            env = child_environment(staging, dependency)
            env.update(
                {
                    "AUTOBLADE_FREECAD_REQUEST": str(staging / "request.json"),
                    "AUTOBLADE_FREECAD_CUSTOM": "1" if custom else "0",
                    "AUTOBLADE_FREECAD_KEEP_FAILED": "1"
                    if job.keep_failed_part
                    else "0",
                }
            )
            command = build_command(
                runner=Path(__file__).with_name("runner.py"),
                staging=staging,
                dependency=dependency,
                app_id=job.freecad_app_id,
            )
            code, stdout, stderr = run_process(
                command, env=env, timeout=job.timeout_seconds
            )
            diagnostics = stdout + "\n" + stderr
            try:
                value = json.loads(
                    (staging / "result.json").read_text(encoding="utf-8")
                )
                result = validate_result(
                    value,
                    digest=request_sha256(request),
                    dependency_digest=dependency_digest,
                    custom=custom,
                )
            except (OSError, ValueError, TypeError, KeyError) as error:
                raise BackendError(
                    BackendName.FREECAD,
                    "protocol",
                    f"Invalid FreeCAD result: {error}",
                    diagnostics=diagnostics,
                ) from error
            if code != 0:
                raise BackendError(
                    BackendName.FREECAD,
                    "protocol",
                    f"FreeCAD exited with code {code} despite a success result.",
                    diagnostics=diagnostics,
                )
            validate_artifacts(
                staging, result, tuple(path.name for path in job.output_paths)
            )
            publish(staging, job.output_paths)
        except BaseException as error:
            retain = (
                isinstance(error, BackendError) and error.code == "cleanup"
            ) or getattr(error, "cleanup_failed", False)
            if job.keep_failed_part and not isinstance(error, KeyboardInterrupt):
                try:
                    snapshot = preserve_failed_model(staging, job.output_paths[0])
                    if snapshot:
                        error.add_note(f"Failed model saved: {snapshot}")
                        warnings.warn(f"Failed model saved: {snapshot}", stacklevel=2)
                except Exception as snapshot_error:
                    error.add_note(
                        f"Failed model snapshot could not be saved: {snapshot_error}"
                    )
            if isinstance(error, BackendError):
                # 结构化错误不能丢掉 stdout/stderr；verbose 必须能复查完整子进程输出。
                if diagnostics and diagnostics != error.diagnostics:
                    error.diagnostics = diagnostics + "\n" + error.diagnostics
                error.verbose = job.verbose
            raise
        finally:
            active_error = sys.exception()
            if job.verbose and diagnostics and active_error is None:
                print(diagnostics)
            if not retain:
                try:
                    shutil.rmtree(staging)
                except OSError as cleanup:
                    if active_error is not None:
                        active_error.add_note(
                            f"Staging cleanup failed at {staging}: {cleanup}"
                        )
                    else:
                        raise BackendError(
                            BackendName.FREECAD,
                            "cleanup",
                            f"Staging cleanup failed at {staging}: {cleanup}",
                        ) from cleanup


def probe_backend(output_dir: Path, *, app_id: str, timeout: float = 60) -> str:
    """在目标文件系统运行独立短探针，返回 CAD/NumPy 版本。"""
    dependency = bundled_dependency()
    validate_curveswb_checkout(dependency)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".autoblade-doctor-", dir=output_dir
    ) as temporary:
        staging = Path(temporary)
        command = build_command(
            runner=Path(__file__).with_name("probe.py"),
            staging=staging,
            dependency=dependency,
            app_id=app_id,
        )
        code, stdout, stderr = run_process(
            command,
            env=child_environment(staging, dependency),
            timeout=min(timeout, 60),
        )
        try:
            result = json.loads((staging / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BackendError(
                BackendName.FREECAD,
                "protocol",
                f"FreeCAD probe result is missing or invalid: {error}",
                diagnostics=stdout + stderr,
            ) from error
        if (
            code != 0
            or result.get("schema_version") != "autoblade.freecad/probe/v1"
            or result.get("status") != "passed"
        ):
            raise BackendError(
                BackendName.FREECAD,
                "unavailable",
                f"FreeCAD probe failed: {result.get('error', code)}",
            )
        version = tuple(int(part) for part in result["freecad_version"][:3])
        if version < (1, 1, 0):
            raise BackendError(
                BackendName.FREECAD, "unavailable", "FreeCAD >= 1.1 is required."
            )
        return f"FreeCAD {'.'.join(str(v) for v in version)}; NumPy {result['numpy_version']}; FCStd create/reopen passed"
