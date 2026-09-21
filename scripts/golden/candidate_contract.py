"""未批准候选的只读契约，供 Host 与独立 FreeCAD 解释器共用。

候选只能产生测量证据，几何适用性由用户判断。人工批准前，输入与 CAD 产物
均留在忽略的 output 目录，不自动成为公开黄金基线。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

try:
    from .fixture import fixture_path, sha256
except ImportError:
    from fixture import fixture_path, sha256


CANDIDATE_SCHEMA = "autoblade.golden.candidate/v1"
PENDING = "awaiting_user_approval"


def load_candidate(case: Path, *, require_catia: bool = True) -> dict:
    """核对候选输入及可选 CATIA 原始文件，绝不借用黄金 schema 冒充批准。"""
    data = json.loads((case / "candidate.json").read_text(encoding="utf-8"))
    if data["schema"] != CANDIDATE_SCHEMA or data["approval_status"] != PENDING:
        raise ValueError("Expected an explicitly unapproved candidate.")
    for name, digest in data["files"].items():
        if sha256(fixture_path(case, name).read_bytes()) != digest:
            raise ValueError(f"Candidate input fingerprint mismatch: {name}")
    if require_catia:
        record = json.loads((case / "catia/record.json").read_text(encoding="utf-8"))
        if record["status"] != "generated_candidate":
            raise ValueError("CATIA candidate generation did not complete.")
        if record["input_manifest_sha256"] != sha256(
            (case / "candidate.json").read_bytes()
        ):
            raise ValueError("CATIA candidate input identity changed.")
        for name, digest in record["artifacts_sha256"].items():
            if sha256(fixture_path(case, "catia/" + name).read_bytes()) != digest:
                raise ValueError(f"CATIA candidate fingerprint mismatch: {name}")
        if set(record["artifacts_sha256"]) != {"blade.CATPart", "blade.stp"}:
            raise ValueError("CATIA candidate artifact set is incomplete.")
    return data


def affine_residual(base: dict, transformed: dict, transform: dict) -> dict:
    """核对体积 scale³ 和质心刚体变换；属性来自 CAD 重开，位置单位 mm。

    transform 的平移使用输入契约的 m；转换为 mm 后绕 X 轴旋转，保持产品的
    旋转→缩放→平移顺序。比较原生与 CATIA 时分别调用，不能互相抵消误差。
    """
    scale = transform["scale"]
    angle = math.radians(transform["rotation_x_deg"])
    x, y, z = base["center_of_mass_mm"]
    rotated = (
        x,
        y * math.cos(angle) - z * math.sin(angle),
        y * math.sin(angle) + z * math.cos(angle),
    )
    expected = [
        scale * value + offset * 1000
        for value, offset in zip(rotated, transform["translation_m"], strict=True)
    ]
    volume = abs(transformed["volume_mm3"] / (base["volume_mm3"] * scale**3) - 1)
    centroid = max(
        abs(actual - target)
        for actual, target in zip(
            transformed["center_of_mass_mm"], expected, strict=True
        )
    )
    if not math.isfinite(volume) or not math.isfinite(centroid):
        raise ValueError("Non-finite affine residual.")
    return {
        "volume_relative": volume,
        "centroid_max_mm": centroid,
        "expected_centroid_mm": expected,
    }
