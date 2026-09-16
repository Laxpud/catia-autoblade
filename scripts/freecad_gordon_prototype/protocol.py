"""FreeCAD Gordon 原型的严格 JSON 请求契约。

本模块只依赖 Python 标准库，Host 端和 ``FreeCADCmd`` 子进程共用同一验证逻辑。
它不是 ``0.3.0`` 的最终公共协议；阶段 2 结束前仍允许依据真实 CAD 证据调整。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path, PurePath
from typing import Any


REQUEST_SCHEMA = "autoblade.freecad-gordon-prototype/request/v2"
RESULT_SCHEMA = "autoblade.freecad-gordon-prototype/result/v2"
ALGORITHM_ID = "curveswb-gordon-builder-explicit-parameters/v1"
CURVESWB_COMMIT = "e4972f761d126901d13b3a72be64eb14f7d51c92"
CURVESWB_VERSION = "0.6.81"

# Runner 实际导入的最小源码闭包。Host 和 Child 都校验摘要，防止一个同名工作台
# 悄悄改变展向插值或连续性行为。摘要对应上方固定 commit 的逐字节文件。
CURVESWB_FILE_SHA256 = {
    "freecad/Curves/BSplineAlgorithms.py": (
        "c7571770f9ac7feb53dc3c15070da5971ef5ec96625c3a94b194aadd0f077a3d"
    ),
    "freecad/Curves/BSplineApproxInterp.py": (
        "08658bc981adbfd7f834a190e3830f5eca10e6413875530738cac43658ab6d10"
    ),
    "freecad/Curves/__init__.py": (
        "2e1489b22e21043e706b923c0d41e6a65e4bf8e3963dfa9fbe96b74c9d1f57aa"
    ),
    "freecad/Curves/curve_network_sorter.py": (
        "e447f52fe809e9dccb843927fb2f83aee0c69814d08aaf6e4cb530a35bccdacc"
    ),
    "freecad/Curves/gordon.py": (
        "6b592dbf322ebb7c99f8027be6c79c8e818b5310fe99bd9df93b93541d6b7423"
    ),
    "freecad/Curves/nurbs_tools.py": (
        "e98b66ea4730d006b1cab432789a34456146d0cff1c703aa8390a9e263a1f3ee"
    ),
    "freecad/Curves/version.py": (
        "dae96e30277186f4b1ca63146043d97bc69d78836cade5e02cbd05e5f81ed890"
    ),
}


class ProtocolError(ValueError):
    """请求违反显式协议时使用的稳定错误类型。"""


def canonical_json(value: Mapping[str, Any]) -> str:
    """返回用于摘要和 FCStd 嵌入的稳定 JSON 表示。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def request_sha256(request: Mapping[str, Any]) -> str:
    """计算与输入路径和 JSON 格式无关的请求摘要。"""
    return hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()


def validate_curveswb_checkout(root: Path) -> dict[str, str]:
    """验证固定 CurvesWB 最小源码闭包并返回实际摘要。

    ``PurePath`` 的标注表达路径只参与受限的逐文件读取；调用方不得把该目录当作
    自由 Python 插件入口。这里不依赖 ``git``，因此发布副本也能验证同一源码。
    """
    actual: dict[str, str] = {}
    for relative, expected in CURVESWB_FILE_SHA256.items():
        path = root / relative
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise ProtocolError(
                f"CurvesWB dependency file is unavailable: {relative}: {error}"
            ) from error
        if digest != expected:
            raise ProtocolError(
                "CurvesWB dependency fingerprint mismatch for "
                f"{relative}: expected {expected}, found {digest}"
            )
        actual[relative] = digest
    return actual


def validate_request(value: Any) -> dict[str, Any]:
    """严格验证并返回请求；未知字段和弱类型都立即失败。"""
    request = _mapping(value, "request")
    _exact_keys(
        request,
        {
            "schema_version",
            "length_unit",
            "trailing_edge_topology",
            "airfoils",
            "sections",
            "modeling",
            "artifacts",
            "source",
        },
        "request",
    )
    _literal(request["schema_version"], REQUEST_SCHEMA, "schema_version")
    _literal(request["length_unit"], "m", "length_unit")
    topology = request["trailing_edge_topology"]
    if topology not in {"sharp", "blunt"}:
        raise ProtocolError(
            "trailing_edge_topology must be exactly 'sharp' or 'blunt'"
        )

    airfoils = _mapping(request["airfoils"], "airfoils")
    if not airfoils:
        raise ProtocolError("airfoils must contain at least one entry")
    for filename, raw_airfoil in airfoils.items():
        if not isinstance(filename, str) or not filename:
            raise ProtocolError("airfoil keys must be non-empty strings")
        airfoil = _mapping(raw_airfoil, f"airfoils.{filename}")
        _exact_keys(
            airfoil,
            {"source_sha256", "point_count", "points"},
            f"airfoils.{filename}",
        )
        _sha256(airfoil["source_sha256"], f"airfoils.{filename}.source_sha256")
        points = _sequence(airfoil["points"], f"airfoils.{filename}.points")
        if len(points) < 3:
            raise ProtocolError(f"airfoils.{filename}.points must contain >= 3 points")
        if airfoil["point_count"] != len(points):
            raise ProtocolError(
                f"airfoils.{filename}.point_count does not match points"
            )
        normalized_points = [
            _point(point, f"airfoils.{filename}.points[{index}]")
            for index, point in enumerate(points)
        ]
        is_closed = normalized_points[0] == normalized_points[-1]
        if (topology == "sharp") != is_closed:
            raise ProtocolError(
                f"airfoils.{filename} does not match {topology} trailing-edge topology"
            )

    sections = _sequence(request["sections"], "sections")
    if len(sections) < 2:
        raise ProtocolError("sections must contain at least two entries")
    previous_idx = 0
    for index, raw_section in enumerate(sections):
        path = f"sections[{index}]"
        section = _mapping(raw_section, path)
        _exact_keys(
            section,
            {
                "idx",
                "airfoil_filename",
                "chord_m",
                "translate_x_m",
                "translate_y_m",
                "translate_z_m",
                "rotation_deg",
            },
            path,
        )
        idx = section["idx"]
        if isinstance(idx, bool) or not isinstance(idx, int) or idx <= previous_idx:
            raise ProtocolError(f"{path}.idx must be a strictly increasing integer")
        previous_idx = idx
        filename = section["airfoil_filename"]
        if not isinstance(filename, str) or filename not in airfoils:
            raise ProtocolError(f"{path}.airfoil_filename must reference airfoils")
        if _finite(section["chord_m"], f"{path}.chord_m") <= 0:
            raise ProtocolError(f"{path}.chord_m must be greater than zero")
        for field in (
            "translate_x_m",
            "translate_y_m",
            "translate_z_m",
            "rotation_deg",
        ):
            _finite(section[field], f"{path}.{field}")

    modeling = _mapping(request["modeling"], "modeling")
    _exact_keys(
        modeling,
        {
            "algorithm",
            "profile_interpolation",
            "spanwise_interpolation",
            "continuity_contract",
            "relative_network_tolerance",
            "parameter_tolerance",
            "step_schema",
            "rebuild_semantics",
        },
        "modeling",
    )
    _literal(modeling["algorithm"], ALGORITHM_ID, "modeling.algorithm")
    _literal(
        modeling["profile_interpolation"],
        "occ-bspline-global-interpolation-with-explicit-region-arc-parameters",
        "modeling.profile_interpolation",
    )
    _literal(
        modeling["spanwise_interpolation"],
        "gordon-builder-with-shared-cumulative-guide-distance-parameters",
        "modeling.spanwise_interpolation",
    )
    _literal(
        modeling["continuity_contract"],
        "report-bspline-knot-continuity;require-interior-c2-per-surface",
        "modeling.continuity_contract",
    )
    _literal(modeling["step_schema"], "AP242DIS", "modeling.step_schema")
    _literal(
        modeling["rebuild_semantics"],
        "static-shape-with-embedded-request-and-pinned-external-runner",
        "modeling.rebuild_semantics",
    )
    relative_tolerance = _finite(
        modeling["relative_network_tolerance"],
        "modeling.relative_network_tolerance",
    )
    if not 0 < relative_tolerance < 1:
        raise ProtocolError(
            "modeling.relative_network_tolerance must be between zero and one"
        )
    if _finite(
        modeling["parameter_tolerance"], "modeling.parameter_tolerance"
    ) <= 0:
        raise ProtocolError("modeling.parameter_tolerance must be greater than zero")
    artifacts = _mapping(request["artifacts"], "artifacts")
    _exact_keys(artifacts, {"native_model", "step"}, "artifacts")
    _artifact_basename(artifacts["native_model"], ".FCStd", "artifacts.native_model")
    _artifact_basename(artifacts["step"], ".stp", "artifacts.step")

    source = _mapping(request["source"], "source")
    required_source = {"blade_sections", "blade_sections_sha256"}
    allowed_source = required_source | {"derived_transform"}
    actual_source = set(source)
    if not required_source.issubset(actual_source) or not actual_source.issubset(
        allowed_source
    ):
        missing = ", ".join(sorted(required_source - actual_source)) or "none"
        unknown = ", ".join(sorted(actual_source - allowed_source)) or "none"
        raise ProtocolError(
            f"source fields differ: missing [{missing}], unknown [{unknown}]"
        )
    if not isinstance(source["blade_sections"], str) or not source["blade_sections"]:
        raise ProtocolError("source.blade_sections must be a non-empty basename")
    if PurePath(source["blade_sections"]).name != source["blade_sections"]:
        raise ProtocolError("source.blade_sections must not contain a path")
    _sha256(source["blade_sections_sha256"], "source.blade_sections_sha256")
    if "derived_transform" in source:
        transform = _mapping(source["derived_transform"], "source.derived_transform")
        _exact_keys(
            transform,
            {
                "scale",
                "rotation_x_deg",
                "translate_x_m",
                "translate_y_m",
                "translate_z_m",
            },
            "source.derived_transform",
        )
        if _finite(transform["scale"], "source.derived_transform.scale") <= 0:
            raise ProtocolError(
                "source.derived_transform.scale must be greater than zero"
            )
        for field in (
            "rotation_x_deg",
            "translate_x_m",
            "translate_y_m",
            "translate_z_m",
        ):
            _finite(transform[field], f"source.derived_transform.{field}")
    return request


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError(f"{path} must be an object")
    return value


def _sequence(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProtocolError(f"{path} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        unknown = ", ".join(sorted(actual - expected)) or "none"
        raise ProtocolError(
            f"{path} fields differ: missing [{missing}], unknown [{unknown}]"
        )


def _literal(value: Any, expected: str, path: str) -> None:
    if value != expected:
        raise ProtocolError(f"{path} must be exactly {expected!r}")


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ProtocolError(f"{path} must be a finite number")
    return result


def _point(value: Any, path: str) -> tuple[float, float, float]:
    point = _sequence(value, path)
    if len(point) != 3:
        raise ProtocolError(f"{path} must contain exactly three coordinates")
    return tuple(_finite(coordinate, f"{path}[{index}]") for index, coordinate in enumerate(point))  # type: ignore[return-value]


def _sha256(value: Any, path: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProtocolError(f"{path} must be a lowercase SHA-256 hex digest")


def _artifact_basename(value: Any, suffix: str, path: str) -> None:
    if not isinstance(value, str) or PurePath(value).name != value:
        raise ProtocolError(f"{path} must be a basename")
    if not value.endswith(suffix):
        raise ProtocolError(f"{path} must end with {suffix}")
