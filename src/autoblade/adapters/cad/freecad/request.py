"""从已经闭合的 AutoBlade 输入计划生成内部 Gordon 请求。"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from autoblade.core.geometry import transform_point
from autoblade.core.input_plan import BladeInputPlan

from .protocol import ALGORITHM_ID, REQUEST_SCHEMA, validate_request


def build_request(
    plan: BladeInputPlan,
    *,
    native_model: str = "blade.FCStd",
    step: str = "blade.stp",
) -> dict[str, Any]:
    """序列化闭合任务，不泄漏路径，也不让 Runner 重新发现 CSV。

    原始 CSV 的 basename 与摘要只用于审计；全部建模坐标和截面参数已嵌入请求，
    因而 Child 端不依赖 Host 工作区或配置目录。
    """
    request: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA,
        "length_unit": "m",
        "trailing_edge_topology": "sharp" if plan.is_sharp else "blunt",
        "airfoils": {
            airfoil.filename: {
                "source_sha256": airfoil.source_sha256,
                "point_count": len(airfoil.points),
                "points": [list(point) for point in airfoil.points],
            }
            for airfoil in plan.airfoils
        },
        "sections": [dict(section) for section in plan.sections],
        "modeling": {
            "algorithm": ALGORITHM_ID,
            "profile_interpolation": (
                "occ-bspline-global-interpolation-with-explicit-region-arc-parameters"
            ),
            "spanwise_interpolation": (
                "gordon-builder-with-shared-cumulative-guide-distance-parameters"
            ),
            "continuity_contract": (
                "report-bspline-knot-continuity;require-interior-c2-per-surface"
            ),
            "relative_network_tolerance": 1e-5,
            "parameter_tolerance": 1e-10,
            "step_schema": "AP242DIS",
            "step_writer": {
                "precision_mode": 2,
                "precision_mm": 1e-7,
                "surfacecurve_mode": 1,
                "length_unit": "mm",
            },
            "rebuild_semantics": (
                "static-shape-with-embedded-request-and-pinned-external-runner"
            ),
        },
        "artifacts": {"native_model": native_model, "step": step},
        "source": {
            "blade_sections": plan.blade_sections_path.name,
            "blade_sections_sha256": plan.blade_sections_sha256,
        },
    }
    return validate_request(request)


def apply_global_transform(
    request: dict[str, Any],
    *,
    scale: float,
    rotation_x_deg: float,
    translate_x_m: float,
    translate_y_m: float,
    translate_z_m: float,
) -> dict[str, Any]:
    """派生明显变换案例，并在 source 中保留可复查的生成参数。"""
    values = {
        "scale": scale,
        "rotation_x_deg": rotation_x_deg,
        "translate_x_m": translate_x_m,
        "translate_y_m": translate_y_m,
        "translate_z_m": translate_z_m,
    }
    if any(
        isinstance(value, bool) or not math.isfinite(value) for value in values.values()
    ):
        raise ValueError("Global transform values must be finite numbers.")
    if scale <= 0:
        raise ValueError("Global transform scale must be greater than zero.")

    transformed = deepcopy(validate_request(request))
    for section in transformed["sections"]:
        position = transform_point(
            section["translate_x_m"],
            section["translate_y_m"],
            section["translate_z_m"],
            rotation_x_deg,
            scale,
            translate_x_m,
            translate_y_m,
            translate_z_m,
        )
        section["translate_x_m"], section["translate_y_m"], section["translate_z_m"] = (
            position
        )
        section["rotation_deg"] += rotation_x_deg
        section["chord_m"] *= scale
    transformed["source"]["derived_transform"] = values
    return validate_request(transformed)
