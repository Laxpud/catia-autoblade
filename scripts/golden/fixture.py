"""黄金夹具的字节身份、许可和测量契约，默认 pytest 无需加载 CAD。

STEP 摘要用于证明基线身份；跨后端几何比较只使用测量值，不比较 STEP 字节。
manifest 固定输入与采样方法。本模块只检查报告完整性，模型适用性由人类判断。
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re


SCHEMA = "autoblade.golden/v2"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASE = ROOT / "tests/fixtures/golden/multi-sharp-89"
DIRECTIONS = ("candidate_to_reference", "reference_to_candidate")


def sha256(data: bytes) -> str:
    """计算原始字节摘要；调用者不能隐式规范化 STEP 的换行。"""
    return hashlib.sha256(data).hexdigest()


def step_data(data: bytes) -> bytes:
    """只接受当前获批文件的单一 DATA 段，保留全部实体字节与行尾。"""
    marker = re.compile(rb"(?m)^DATA;\r?\n")
    matches = list(marker.finditer(data))
    if len(matches) != 1 or not data.startswith(b"ISO-10303-21;"):
        raise ValueError("Expected exactly one STEP DATA section.")
    return data[matches[0].start() :]


def sanitize_step(data: bytes, *, original_sha256: str) -> bytes:
    """对已批准摘要只替换 HEADER/FILE_NAME 的路径，拒绝重导出或修改几何。

    此流程不推定新 CATIA 输出已获批准。原始摘要必须由调用者从批准记录提供，
    输出仍需记录新摘要并通过真实 CAD 重开审计。
    """
    if sha256(data) != original_sha256:
        raise ValueError("Original STEP does not match the approved SHA-256.")
    tail = step_data(data)
    header = data[: -len(tail)]
    header, count = re.subn(
        rb"(?m)^FILE_NAME\('(?:[^']|'')*'",
        b"FILE_NAME('catia.stp'",
        header,
    )
    if count != 1:
        raise ValueError("Expected exactly one STEP FILE_NAME header.")
    return header + tail


def _finite(value: object, label: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or (positive and value == 0)
    ):
        raise ValueError(f"Invalid finite numeric value: {label}")
    return float(value)


def fixture_path(case: Path, value: str) -> Path:
    """夹具引用只能落在自身目录，拒绝绝对路径、回溯和符号链接逃逸。"""
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in value
        or ":" in value
        or relative.as_posix() != value
    ):
        raise ValueError(f"Unsafe fixture path: {value}")
    path = case / value
    if not path.resolve(strict=True).is_relative_to(case.resolve()):
        raise ValueError(f"Fixture path escapes its directory: {value}")
    if any(part.is_symlink() for part in (path, *path.parents) if part != case.parent):
        raise ValueError(f"Fixture path must not be a symlink: {value}")
    return path


def load_fixture(case: Path = DEFAULT_CASE) -> dict:
    """在创建 CAD 进程前检查全部公开文件、许可引用、测量计划与人工判断策略。"""
    manifest = json.loads((case / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema"] != SCHEMA:
        raise ValueError("Unknown golden fixture schema.")
    files = manifest["files"]
    actual = {
        path.relative_to(case).as_posix() for path in case.rglob("*") if path.is_file()
    } - {"manifest.json"}
    if set(files) != actual:
        raise ValueError("Golden fixture contains missing or unlisted files.")
    for name, digest in files.items():
        path = fixture_path(case, name)
        if path.suffix not in {".csv", ".stp", ".json", ".md"}:
            raise ValueError(f"Unexpected golden fixture file type: {name}")
        if sha256(path.read_bytes()) != digest:
            raise ValueError(f"Golden fixture SHA-256 mismatch: {name}")
    for name in (
        manifest["baseline"]["step"],
        manifest["input"]["sections"],
        manifest["authorization"]["notice"],
        manifest["reference_metrics"],
        *manifest["input"]["airfoils"],
    ):
        if name not in files:
            raise ValueError(f"Fixture reference is not fingerprinted: {name}")
    baseline = fixture_path(case, manifest["baseline"]["step"]).read_bytes()
    if sha256(step_data(baseline)) != manifest["baseline"]["data_sha256"]:
        raise ValueError("STEP DATA fingerprint mismatch.")
    if b"FILE_NAME('catia.stp'," not in baseline:
        raise ValueError("Golden STEP header was not sanitized.")
    if manifest["decision_policy"] != "human_only":
        raise ValueError("Golden measurements require human usability judgment.")
    # 旧阈值仅保留历史证据，不参与当前报告状态或进程退出码。
    for layer in manifest.get("historical_tolerances", {}).values():
        for key, value in layer.items():
            _finite(value, key, positive=True)
    sampling = manifest["sampling"]
    _finite(sampling["deflection_mm"], "deflection_mm", positive=True)
    for key in ("surface_samples", "section_samples"):
        if type(sampling[key]) is not int or sampling[key] < 2:
            raise ValueError(f"Invalid sample budget: {key}")
    stations = sampling["stations"]
    if not stations or len({row["x_mm"] for row in stations}) != len(stations):
        raise ValueError("Fixed stations must be nonempty and unique.")
    for row in stations:
        if type(row["allow_incomplete"]) is not bool or not math.isfinite(row["x_mm"]):
            raise ValueError("Invalid station contract.")
    offsets = sampling["retry_offsets_mm"]
    if not offsets or offsets[0] != 0 or not all(math.isfinite(x) for x in offsets):
        raise ValueError("Section retries must begin at the requested plane.")
    return manifest


def validate_measurements(report: dict, manifest: dict) -> dict:
    """检查报告身份之外的数据完整性，返回覆盖统计，不按几何误差大小裁决。

    所有预定站位必须有记录。截面提取不完整时保留曲面诊断并显式列出缺口；
    缺口或较大偏差均不等同于模型不可用，缺失记录/NaN 则表示报告无法消费。
    """
    if set(report["properties"]) != {"native", "step", "catia"}:
        raise ValueError("Missing shape properties.")
    for name, properties in report["properties"].items():
        if (
            properties["valid"] is not True
            or properties["closed"] is not True
            or type(properties["solids"]) is not int
            or properties["solids"] != 1
        ):
            raise ValueError(f"{name}: expected one valid closed solid for measurement")
        _finite(properties["volume_mm3"], name + ".volume_mm3", positive=True)
        for key, count in (("center_of_mass_mm", 3), ("bounding_box_mm", 6)):
            values = properties[key]
            if len(values) != count or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in values
            ):
                raise ValueError(f"Invalid coordinate measurements: {name}.{key}")

    def distances(values: dict, budget: int) -> None:
        for direction in DIRECTIONS:
            row = values[direction]
            if type(row["samples"]) is not int or not 2 <= row["samples"] <= budget:
                raise ValueError("Invalid distance sample coverage.")
            _finite(row["max_mm"], direction + ".max_mm")
            _finite(row["rms_mm"], direction + ".rms_mm")

    for layer in ("exchange", "cross_backend"):
        measured = report[layer]
        for key in ("volume_relative", "centroid_max_mm", "bbox_max_mm"):
            _finite(measured[key], layer + "." + key)
        distances(measured["surface"], manifest["sampling"]["surface_samples"])
    expected = manifest["sampling"]["stations"]
    stations = report["stations"]
    if [row["requested_x_mm"] for row in stations] != [row["x_mm"] for row in expected]:
        raise ValueError("Fixed station coverage differs from the manifest.")
    incomplete = []
    for row in stations:
        if type(row["complete"]) is not bool:
            raise ValueError("Invalid station completeness.")
        if not row["complete"]:
            incomplete.append(row["requested_x_mm"])
        distances(
            row["section"] if row["complete"] else row["surface_diagnostic"],
            manifest["sampling"]["section_samples"],
        )
    return {
        "planned_stations": len(expected),
        "recorded_stations": len(stations),
        "complete_stations": len(stations) - len(incomplete),
        "incomplete_stations_mm": incomplete,
    }
