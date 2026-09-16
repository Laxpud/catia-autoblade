"""比较 v2 Gordon FCStd 与一套 CATIA STEP 候选基线。

由 ``FreeCADCmd`` 直接执行。探针只读两个已有制品，报告实体属性、确定性有限
曲面样本和翼型切换区固定 X 截面距离；它不修改模型，也不把有限采样结果声明为
连续 Hausdorff 上界。CATIA 文件能否成为黄金基线仍需独立的许可与工程批准。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import traceback
from pathlib import Path
from typing import Any

import FreeCAD as App
import Part


GLOBAL_SAMPLE_LIMIT = 400
SECTION_SAMPLE_LIMIT = 240
INITIAL_TRANSITION_FRACTIONS = tuple(index / 20 for index in range(1, 20))
REFINEMENT_OFFSETS = (-0.01, -0.005, 0.005, 0.01)
SECTION_PLANE_RETRY_OFFSETS_MM = (0.0, 1e-4, -1e-4, 1e-3, -1e-3)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _point_list(point: Any) -> list[float]:
    return [point.x, point.y, point.z]


def _rms(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values))


def _make_x_plane(x_mm: float) -> Any:
    """创建覆盖当前公开叶片尺寸的 X 常量截面平面。"""
    plane = Part.makePlane(4000, 4000, App.Vector(-2000, -2000, 0))
    plane.rotate(App.Vector(), App.Vector(0, 1, 0), 90)
    plane.translate(App.Vector(x_mm, 0, 0))
    return plane


def _uniform_subset(points: list[Any], limit: int) -> list[Any]:
    if len(points) <= limit:
        return points
    return [
        points[round(index * (len(points) - 1) / (limit - 1))]
        for index in range(limit)
    ]


def _surface_points(shape: Any) -> list[Any]:
    """固定 deflection 后等索引抽样；这是可复查有限样本，不做面积加权。"""
    points, _ = shape.tessellate(0.1)
    return _uniform_subset(points, GLOBAL_SAMPLE_LIMIT)


def _section_points(section: Any) -> list[Any]:
    """按边长分配固定预算，避免拓扑分段数改变时过度偏向短边。"""
    edges = list(section.Edges)
    total_length = sum(edge.Length for edge in edges)
    if not edges or total_length <= 0:
        raise ValueError("Section has no measurable edges.")
    points = []
    for edge in edges:
        count = max(3, round(SECTION_SAMPLE_LIMIT * edge.Length / total_length))
        points.extend(edge.discretize(Number=count))
    return _uniform_subset(points, SECTION_SAMPLE_LIMIT)


def _distance_summary(points: list[Any], target: Any) -> dict[str, Any]:
    rows = []
    for index, point in enumerate(points):
        distance, pairs, _ = Part.Vertex(point).distToShape(target)
        rows.append((distance, index, point, pairs[0][1]))
    worst = max(rows, key=lambda row: row[0])
    return {
        "samples": len(rows),
        "max_mm": worst[0],
        "rms_mm": _rms([row[0] for row in rows]),
        "worst_sample_index": worst[1],
        "worst_source_mm": _point_list(worst[2]),
        "worst_target_mm": _point_list(worst[3]),
    }


def _section_state(section: Any) -> dict[str, Any]:
    groups = Part.sortEdges(section.Edges)
    closed_groups = 0
    for group in groups:
        try:
            closed_groups += int(Part.Wire(group).isClosed())
        except Exception:
            pass
    return {
        "edges": len(section.Edges),
        "connected_groups": len(groups),
        "closed_groups": closed_groups,
        "length_mm": section.Length,
    }


def _transition_ranges(request: dict[str, Any]) -> list[dict[str, Any]]:
    """从闭合请求推导相邻翼型文件发生变化的展向区间。"""
    sections = request["sections"]
    ranges = []
    for left, right in zip(sections, sections[1:], strict=False):
        if left["airfoil_filename"] == right["airfoil_filename"]:
            continue
        ranges.append(
            {
                "left_section": left["idx"],
                "right_section": right["idx"],
                "left_airfoil": left["airfoil_filename"],
                "right_airfoil": right["airfoil_filename"],
                "left_x_mm": left["translate_x_m"] * 1000,
                "right_x_mm": right["translate_x_m"] * 1000,
            }
        )
    return ranges


def _measure_station(
    gordon: Any,
    catia: Any,
    gordon_surface: Any,
    catia_surface: Any,
    *,
    fraction: float,
    left_x_mm: float,
    right_x_mm: float,
) -> dict[str, Any]:
    requested_x_mm = left_x_mm + (right_x_mm - left_x_mm) * fraction
    attempts = []
    selected = None
    for offset_mm in SECTION_PLANE_RETRY_OFFSETS_MM:
        x_mm = requested_x_mm + offset_mm
        plane = _make_x_plane(x_mm)
        gordon_section = gordon.section(plane)
        catia_section = catia.section(plane)
        gordon_state = _section_state(gordon_section)
        catia_state = _section_state(catia_section)
        eligible = all(
            state["connected_groups"] == 1 and state["closed_groups"] == 1
            for state in (gordon_state, catia_state)
        )
        attempts.append(
            {
                "offset_mm": offset_mm,
                "gordon_section": gordon_state,
                "catia_section": catia_state,
                "eligible": eligible,
            }
        )
        selected = (
            x_mm,
            offset_mm,
            gordon_section,
            catia_section,
            gordon_state,
            catia_state,
            eligible,
        )
        if eligible:
            break
    assert selected is not None
    (
        x_mm,
        offset_mm,
        gordon_section,
        catia_section,
        gordon_state,
        catia_state,
        eligible,
    ) = selected
    if not gordon_section.Edges or not catia_section.Edges:
        raise ValueError(f"Missing fixed-X section near {requested_x_mm} mm.")
    gordon_points = _section_points(gordon_section)
    catia_points = _section_points(catia_section)
    forward = _distance_summary(gordon_points, catia_section)
    reverse = _distance_summary(catia_points, gordon_section)
    forward_point = App.Vector(*forward["worst_source_mm"])
    reverse_point = App.Vector(*reverse["worst_source_mm"])
    forward["worst_source_to_target_surface_mm"] = Part.Vertex(
        forward_point
    ).distToShape(catia_surface)[0]
    reverse["worst_source_to_target_surface_mm"] = Part.Vertex(
        reverse_point
    ).distToShape(gordon_surface)[0]
    # 固定平面布尔截面偶尔只返回一侧开边。此时点到完整三维曲面的距离仍可作为
    # 诊断，但反向点到残缺截面的距离会产生几十毫米伪峰。双方共享极小平面偏移
    # 重试，仍失败才排除，并让 summary 暴露数量而不是静默跳过。
    return {
        "fraction": fraction,
        "requested_x_mm": requested_x_mm,
        "x_mm": x_mm,
        "plane_offset_mm": offset_mm,
        "section_attempts": attempts,
        "eligible_for_fixed_section_comparison": eligible,
        "gordon_section": gordon_state,
        "catia_section": catia_state,
        "gordon_to_catia": forward,
        "catia_to_gordon": reverse,
    }


def _station_max(station: dict[str, Any]) -> float:
    return max(
        station["gordon_to_catia"]["max_mm"],
        station["catia_to_gordon"]["max_mm"],
    )


def _eligible_stations(stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [
        station
        for station in stations
        if station["eligible_for_fixed_section_comparison"]
    ]
    if not eligible:
        raise ValueError("No complete fixed-X sections were measured.")
    return eligible


def _shape_properties(shape: Any) -> dict[str, Any]:
    box = shape.BoundBox
    return {
        "valid": shape.isValid(),
        "closed": shape.isClosed(),
        "solids": len(shape.Solids),
        "volume_mm3": shape.Volume,
        "center_of_mass_mm": list(shape.Solids[0].CenterOfMass),
        "bounding_box_mm": {
            "x_min": box.XMin,
            "x_max": box.XMax,
            "y_min": box.YMin,
            "y_max": box.YMax,
            "z_min": box.ZMin,
            "z_max": box.ZMax,
        },
    }


def _property_deltas(gordon: dict[str, Any], catia: dict[str, Any]) -> dict[str, Any]:
    center_deltas = [
        left - right
        for left, right in zip(
            gordon["center_of_mass_mm"],
            catia["center_of_mass_mm"],
            strict=True,
        )
    ]
    box_deltas = {
        key: gordon["bounding_box_mm"][key] - catia["bounding_box_mm"][key]
        for key in gordon["bounding_box_mm"]
    }
    return {
        "volume_delta_mm3": gordon["volume_mm3"] - catia["volume_mm3"],
        "volume_relative_to_catia": (
            gordon["volume_mm3"] / catia["volume_mm3"] - 1
        ),
        "center_of_mass_delta_mm": center_deltas,
        "center_of_mass_max_abs_delta_mm": max(map(abs, center_deltas)),
        "bounding_box_delta_mm": box_deltas,
        "bounding_box_max_abs_delta_mm": max(map(abs, box_deltas.values())),
    }


def run() -> None:
    gordon_value = os.environ.get("AUTOBLADE_GORDON_COMPARE_FCSTD")
    catia_value = os.environ.get("AUTOBLADE_GORDON_COMPARE_CATIA_STEP")
    output_value = os.environ.get("AUTOBLADE_GORDON_COMPARE_OUTPUT")
    if not gordon_value or not catia_value or not output_value:
        raise ValueError(
            "AUTOBLADE_GORDON_COMPARE_FCSTD, "
            "AUTOBLADE_GORDON_COMPARE_CATIA_STEP and "
            "AUTOBLADE_GORDON_COMPARE_OUTPUT are required."
        )
    gordon_path = Path(gordon_value).resolve(strict=True)
    catia_path = Path(catia_value).resolve(strict=True)
    output_dir = Path(output_value).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    if result_path.exists():
        raise ValueError(f"Comparison result already exists: {result_path}")

    started = time.monotonic()
    report: dict[str, Any] = {
        "status": "failed",
        "method": {
            "global_surface": (
                "bidirectional deterministic finite samples from 0.1 mm "
                "tessellations to exact target faces"
            ),
            "transition_sections": (
                "fixed-X initial 5% span grid plus local refinement around "
                "each observed grid maximum; finite edge samples to exact target edges"
            ),
            "distance_scope": (
                "finite-sample evidence; not a continuous Hausdorff bound and not a "
                "manufacturing tolerance"
            ),
        },
        "inputs": {
            "gordon_fcstd": str(gordon_path),
            "gordon_fcstd_sha256": _sha256(gordon_path),
            "catia_step": str(catia_path),
            "catia_step_sha256": _sha256(catia_path),
        },
        "freecad_version": list(App.Version()),
        "transitions": [],
    }
    document = None
    try:
        document = App.openDocument(str(gordon_path))
        blade = document.getObject("BladeSolid")
        traceability = document.getObject("Traceability")
        if blade is None or traceability is None:
            raise ValueError("Gordon FCStd lacks BladeSolid or Traceability.")
        request = json.loads(traceability.RebuildRequestJson)
        gordon = blade.Shape
        catia = Part.read(str(catia_path))
        for name, shape in (("gordon", gordon), ("catia", catia)):
            if not shape.isValid() or not shape.isClosed() or len(shape.Solids) != 1:
                raise ValueError(f"{name} input is not one valid closed solid.")
        gordon_surface = Part.makeCompound(gordon.Faces)
        catia_surface = Part.makeCompound(catia.Faces)

        report["request_sha256"] = traceability.RequestSHA256
        report["properties"] = {
            "gordon": _shape_properties(gordon),
            "catia": _shape_properties(catia),
        }
        report["properties"]["deltas"] = _property_deltas(
            report["properties"]["gordon"], report["properties"]["catia"]
        )
        report["global_surface"] = {
            "gordon_to_catia": _distance_summary(
                _surface_points(gordon), catia_surface
            ),
            "catia_to_gordon": _distance_summary(
                _surface_points(catia), gordon_surface
            ),
        }

        for transition in _transition_ranges(request):
            measured: dict[float, dict[str, Any]] = {}
            for fraction in INITIAL_TRANSITION_FRACTIONS:
                station = _measure_station(
                    gordon,
                    catia,
                    gordon_surface,
                    catia_surface,
                    fraction=fraction,
                    left_x_mm=transition["left_x_mm"],
                    right_x_mm=transition["right_x_mm"],
                )
                measured[fraction] = station
                print(
                    transition["left_airfoil"],
                    transition["right_airfoil"],
                    f"fraction={fraction:.6f}",
                    f"max_mm={_station_max(station):.9f}",
                    f"eligible={station['eligible_for_fixed_section_comparison']}",
                    flush=True,
                )
            grid_worst = max(
                _eligible_stations(list(measured.values())), key=_station_max
            )
            for offset in REFINEMENT_OFFSETS:
                fraction = round(grid_worst["fraction"] + offset, 12)
                if not 0 < fraction < 1 or fraction in measured:
                    continue
                measured[fraction] = _measure_station(
                    gordon,
                    catia,
                    gordon_surface,
                    catia_surface,
                    fraction=fraction,
                    left_x_mm=transition["left_x_mm"],
                    right_x_mm=transition["right_x_mm"],
                )
            stations = [measured[key] for key in sorted(measured)]
            eligible = _eligible_stations(stations)
            worst = max(eligible, key=_station_max)
            report["transitions"].append(
                {
                    **transition,
                    "stations": stations,
                    "incomplete_section_stations": [
                        {
                            "fraction": station["fraction"],
                            "requested_x_mm": station["requested_x_mm"],
                            "x_mm": station["x_mm"],
                            "section_attempts": station["section_attempts"],
                            "gordon_section": station["gordon_section"],
                            "catia_section": station["catia_section"],
                            "worst_source_to_target_surface_mm": max(
                                station[direction][
                                    "worst_source_to_target_surface_mm"
                                ]
                                for direction in (
                                    "gordon_to_catia",
                                    "catia_to_gordon",
                                )
                            ),
                        }
                        for station in stations
                        if not station["eligible_for_fixed_section_comparison"]
                    ],
                    "observed_worst": worst,
                }
            )
            result_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )

        all_stations = _eligible_stations([
            station
            for transition in report["transitions"]
            for station in transition["stations"]
        ])
        report["summary"] = {
            "global_surface_max_mm": max(
                report["global_surface"][direction]["max_mm"]
                for direction in ("gordon_to_catia", "catia_to_gordon")
            ),
            "transition_section_max_mm": max(map(_station_max, all_stations)),
            "transition_worst": max(all_stations, key=_station_max),
            "incomplete_section_station_count": sum(
                len(transition["incomplete_section_stations"])
                for transition in report["transitions"]
            ),
        }
        report["status"] = "passed_probe"
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        result_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    key: report.get(key)
                    for key in ("status", "summary", "error", "elapsed_seconds")
                },
                ensure_ascii=False,
                allow_nan=False,
            ),
            flush=True,
        )
        if document is not None:
            App.closeDocument(document.Name)


# FreeCADCmd 直接执行脚本；保持与主 Runner 相同的无入口守卫约束。
run()
