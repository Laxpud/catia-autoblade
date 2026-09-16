"""只消费闭合 JSON 的 FreeCAD Gordon 阶段 2 Runner。

该文件由 ``FreeCADCmd`` 直接执行，末尾无条件调用 ``run``，不依赖普通 Python
入口守卫。它只保存静态几何，但在 FCStd 内嵌完整请求及固定算法身份；声明的重建
方式是再次执行同一个受版本控制 Runner，而不是把 Shape 缓存冒充参数化模型。
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import resource
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from protocol import (  # type: ignore[import-not-found]
    CURVESWB_COMMIT,
    CURVESWB_VERSION,
    RESULT_SCHEMA,
    canonical_json,
    request_sha256,
    validate_curveswb_checkout,
    validate_request,
)

import FreeCAD as App


# STEP 偏好只写入 Launcher 分配的隔离 user.cfg，并在加载 Import 前固定。
App.ParamGet("User parameter:BaseApp/Preferences/Mod/Part/STEP").SetString(
    "Scheme", "AP242DIS"
)
import Import  # noqa: E402
import Part  # noqa: E402


MM_PER_METER = 1000.0
PROFILE_SAMPLES = 30
GUIDE_SAMPLES = 100


def _load_request() -> tuple[dict[str, Any], str]:
    request_path = os.environ.get("AUTOBLADE_PROTOTYPE_REQUEST")
    rebuild_path = os.environ.get("AUTOBLADE_PROTOTYPE_REBUILD_FCSTD")
    if bool(request_path) == bool(rebuild_path):
        raise ValueError(
            "Exactly one prototype request or rebuild FCStd must be provided."
        )
    if request_path:
        value = json.loads(Path(request_path).read_text(encoding="utf-8"))
        return validate_request(value), "closed_json"

    source = App.openDocument(str(Path(rebuild_path).resolve(strict=True)))
    try:
        traceability = source.getObject("Traceability")
        if traceability is None:
            raise ValueError("Rebuild FCStd does not contain Traceability metadata.")
        value = json.loads(traceability.RebuildRequestJson)
        request = validate_request(value)
        if traceability.RequestSHA256 != request_sha256(request):
            raise ValueError("Embedded rebuild request digest does not match metadata.")
        return request, "embedded_fcstd_request"
    finally:
        App.closeDocument(source.Name)


def _configure_curveswb() -> tuple[Path, str]:
    root_value = os.environ.get("AUTOBLADE_PROTOTYPE_CURVESWB_DIR")
    if not root_value:
        raise ValueError("AUTOBLADE_PROTOTYPE_CURVESWB_DIR is required.")
    root = Path(root_value).resolve(strict=True)
    file_digests = validate_curveswb_checkout(root)
    dependency_digest = hashlib.sha256(
        canonical_json(file_digests).encode("utf-8")
    ).hexdigest()

    # CurvesWB 使用 ``freecad`` namespace package；只追加已验证 checkout 的固定目录。
    sys.path.insert(0, str(root))
    import freecad  # type: ignore[import-not-found]

    freecad.__path__.append(str(root / "freecad"))
    return root, dependency_digest


def _transform_point(point_m: list[float], section: dict[str, Any]) -> Any:
    """按领域约定执行绕 X、缩放、平移，并只在此 CAD 边界换算 mm。"""
    px, py, pz = point_m
    angle = math.radians(section["rotation_deg"])
    scale = section["chord_m"] * MM_PER_METER
    return App.Vector(
        px * scale + section["translate_x_m"] * MM_PER_METER,
        (py * math.cos(angle) - pz * math.sin(angle)) * scale
        + section["translate_y_m"] * MM_PER_METER,
        (py * math.sin(angle) + pz * math.cos(angle)) * scale
        + section["translate_z_m"] * MM_PER_METER,
    )


def _interpolate(points: list[Any], parameters: list[float]) -> Any:
    """用调用方提供的共同参数精确插值，禁止 Gordon 内部再次近似重参数化。"""
    curve = Part.BSplineCurve()
    curve.interpolate(
        Points=points,
        Parameters=parameters,
        PeriodicFlag=False,
    )
    return curve


def _normalized_cumulative_parameters(point_sets: list[list[Any]]) -> list[float]:
    """以多条对应折线的平均步长生成严格递增的共同参数。

    对 profile 传入一条折线；对 spanwise guide 同时传入 LE、TE-upper、
    TE-lower。后者用三条边界的平均几何步长，避免任一条 guide 单独决定所有
    截面的 Gordon 参数，同时保证每条 guide 在同一截面使用同一个参数值。
    """
    if not point_sets or len(point_sets[0]) < 2:
        raise ValueError("Parameterization requires at least two points.")
    count = len(point_sets[0])
    if any(len(points) != count for points in point_sets):
        raise ValueError("Parameterization point sets must have equal lengths.")
    increments = []
    for index in range(1, count):
        increment = sum(
            points[index - 1].distanceToPoint(points[index])
            for points in point_sets
        ) / len(point_sets)
        if increment <= 0.0:
            raise ValueError(
                "Consecutive parameterization stations must not all coincide."
            )
        increments.append(increment)
    total = sum(increments)
    cumulative = [0.0]
    for increment in increments:
        cumulative.append(cumulative[-1] + increment / total)
    cumulative[-1] = 1.0
    return cumulative


def _profile_parameters(
    points: list[Any],
    leading_index: int,
    topology: str,
) -> dict[str, list[float]]:
    """定义可审计的 chordwise 参数；钝尾缘固定 LE 参数为 0.5。"""
    if topology == "sharp":
        return {
            "upper": _normalized_cumulative_parameters(
                [points[: leading_index + 1]]
            ),
            "lower": _normalized_cumulative_parameters([points[leading_index:]]),
        }
    upper = _normalized_cumulative_parameters([points[: leading_index + 1]])
    lower = _normalized_cumulative_parameters([points[leading_index:]])
    return {
        "full": [value * 0.5 for value in upper]
        + [0.5 + value * 0.5 for value in lower[1:]]
    }


def _curve_distance_summary(points: list[Any], shape: Any) -> dict[str, Any]:
    distances = [Part.Vertex(point).distToShape(shape)[0] for point in points]
    max_index = max(range(len(distances)), key=distances.__getitem__)
    return {
        "samples": len(distances),
        "max_mm": distances[max_index],
        "max_sample_index": max_index,
        "max_point_mm": list(points[max_index]),
        "rms_mm": math.sqrt(
            sum(distance * distance for distance in distances) / len(distances)
        ),
    }


def _shape_state(shape: Any) -> dict[str, Any]:
    """在几何 gate 失败时保留足以定位拓扑层级的最小状态。"""
    return {
        "shape_type": shape.ShapeType,
        "valid": shape.isValid(),
        "closed": shape.isClosed(),
        "faces": len(shape.Faces),
        "shells": len(shape.Shells),
        "solids": len(shape.Solids),
        "edges": len(shape.Edges),
    }


def _free_edge_states(shell: Any) -> list[dict[str, Any]]:
    """列出 sewing 后只被一个面引用的边，定位未闭合的具体接缝。"""
    groups: list[tuple[Any, int]] = []
    for face in shell.Faces:
        for edge in face.Edges:
            for index, (known, count) in enumerate(groups):
                if edge.isSame(known):
                    groups[index] = (known, count + 1)
                    break
            else:
                groups.append((edge, 1))
    states = []
    for edge, count in groups:
        if count != 1:
            continue
        states.append(
            {
                "length_mm": edge.Length,
                "bounds_mm": {
                    "x": [edge.BoundBox.XMin, edge.BoundBox.XMax],
                    "y": [edge.BoundBox.YMin, edge.BoundBox.YMax],
                    "z": [edge.BoundBox.ZMin, edge.BoundBox.ZMax],
                },
            }
        )
    return states


def _continuity(surface: Any, direction: str) -> dict[str, Any]:
    if direction == "u":
        degree = surface.UDegree
        multiplicities = list(surface.getUMultiplicities())
        knots = list(surface.getUKnots())
    else:
        degree = surface.VDegree
        multiplicities = list(surface.getVMultiplicities())
        knots = list(surface.getVKnots())
    interior = multiplicities[1:-1]
    minimum_order = degree - max(interior) if interior else degree
    return {
        "degree": degree,
        "knots": knots,
        "multiplicities": multiplicities,
        "minimum_interior_continuity_order": minimum_order,
    }


def _find_cap_edge(face: Any, profile: Any) -> Any:
    """用整条曲线距离选根/尖边，避免依赖拓扑编号或截面恰好位于固定 X。"""
    profile_shape = profile.toShape()
    candidates: list[tuple[float, Any]] = []
    for edge in face.Edges:
        points = edge.discretize(Number=11)
        maximum = max(
            Part.Vertex(point).distToShape(profile_shape)[0] for point in points
        )
        candidates.append((maximum, edge))
    return min(candidates, key=lambda item: item[0])[1]


def _find_distinct_boundary_edges(
    face: Any,
    first_reference: Any,
    second_reference: Any,
) -> tuple[Any, Any]:
    """把两个相邻 guide 全局匹配到互不相同的最终曲面边。"""
    references = (first_reference.toShape(), second_reference.toShape())
    scores: list[list[float]] = []
    for reference in references:
        edge_scores = []
        for edge in face.Edges:
            edge_scores.append(
                max(
                    Part.Vertex(point).distToShape(reference)[0]
                    for point in edge.discretize(Number=21)
                )
            )
        scores.append(edge_scores)
    first_index, second_index = min(
        itertools.permutations(range(len(face.Edges)), 2),
        key=lambda pair: scores[0][pair[0]] + scores[1][pair[1]],
    )
    return face.Edges[first_index], face.Edges[second_index]


def _make_cap(
    upper_face: Any,
    lower_face: Any,
    upper_profile: Any,
    lower_profile: Any,
) -> Any:
    upper_edge = _find_cap_edge(upper_face, upper_profile)
    lower_edge = _find_cap_edge(lower_face, lower_profile)
    edges = [upper_edge, lower_edge]
    wire = Part.Wire(edges)
    if not wire.isClosed():
        raise ValueError("Gordon root/tip cap wire is open.")
    return Part.Face(wire)


def _make_open_profile_cap(face: Any, profile: Any) -> Any:
    """用钝尾缘完整开轮廓的最终边和实际端点创建根/尖封盖。"""
    edge = _find_cap_edge(face, profile)
    first_reference = profile.value(profile.FirstParameter)
    last_reference = profile.value(profile.LastParameter)
    edge_endpoints = (
        edge.valueAt(edge.FirstParameter),
        edge.valueAt(edge.LastParameter),
    )
    first = min(
        edge_endpoints,
        key=lambda point: point.distanceToPoint(first_reference),
    )
    last = min(
        edge_endpoints,
        key=lambda point: point.distanceToPoint(last_reference),
    )
    wire = Part.Wire([edge, Part.makeLine(last, first)])
    if not wire.isClosed():
        raise ValueError("Gordon blunt root/tip cap wire is open.")
    return Part.Face(wire)


def _build_geometry(request: dict[str, Any]) -> tuple[Any, dict[str, Any], Any]:
    from freecad.Curves.gordon import (  # type: ignore[import-not-found]
        GordonSurfaceBuilder,
    )

    airfoils = request["airfoils"]
    topology = request["trailing_edge_topology"]
    profile_regions = ("upper", "lower") if topology == "sharp" else ("full",)
    profiles: dict[str, list[Any]] = {region: [] for region in profile_regions}
    guide_points: dict[str, list[Any]] = {
        "leading": [],
        "trailing_upper": [],
        "trailing_lower": [],
    }
    profile_fit: dict[str, list[dict[str, Any]]] = {
        region: [] for region in profile_regions
    }

    # 1. 尖后缘拆成两侧以避开闭合 profile 的多交点；钝后缘保留完整开轮廓，
    #    使 LE 位于同一 Gordon 曲面内部，避免两次独立重参数化产生 LE 裂缝。
    for section in request["sections"]:
        raw_points = airfoils[section["airfoil_filename"]]["points"]
        leading_index = max(range(len(raw_points)), key=lambda index: raw_points[index][1])
        if leading_index in {0, len(raw_points) - 1}:
            raise ValueError(
                f"Section {section['idx']} has no interior leading-edge point."
            )
        transformed = [_transform_point(point, section) for point in raw_points]
        region_points = (
            {
                "upper": transformed[: leading_index + 1],
                "lower": transformed[leading_index:],
            }
            if topology == "sharp"
            else {"full": transformed}
        )
        region_parameters = _profile_parameters(
            transformed,
            leading_index,
            topology,
        )
        for region, points in region_points.items():
            curve = _interpolate(points, region_parameters[region])
            profiles[region].append(curve)
            profile_fit[region].append(
                {
                    "section_idx": section["idx"],
                    **_curve_distance_summary(points, curve.toShape()),
                }
            )
        guide_points["leading"].append(transformed[leading_index])
        guide_points["trailing_upper"].append(transformed[0])
        guide_points["trailing_lower"].append(transformed[-1])

    # 2. LE/TE 是真实曲面网络约束。钝轮廓使用三条 guide 构成单张 full-wrap
    #    曲面；尖轮廓仍用共享 LE/TE 的上下两张曲面。
    span_parameters = _normalized_cumulative_parameters(list(guide_points.values()))
    guides = {
        name: _interpolate(points, span_parameters)
        for name, points in guide_points.items()
    }
    options = request["modeling"]
    faces: dict[str, Any] = {}
    surfaces: dict[str, Any] = {}
    surface_holds: dict[str, list[dict[str, Any]]] = {
        region: [] for region in profile_regions
    }
    for region in profile_regions:
        network_guides = (
            [guides["trailing_upper"], guides["leading"]]
            if region == "upper"
            else [guides["leading"], guides["trailing_lower"]]
            if region == "lower"
            else [
                guides["trailing_upper"],
                guides["leading"],
                guides["trailing_lower"],
            ]
        )
        chordwise_parameters = (
            [0.0, 1.0]
            if topology == "sharp"
            else [0.0, 0.5, 1.0]
        )
        builder = GordonSurfaceBuilder(
            profiles[region],
            network_guides,
            chordwise_parameters,
            span_parameters,
            tol=options["relative_network_tolerance"],
            par_tol=options["parameter_tolerance"],
        )
        surface = builder.surface_gordon()
        face = surface.toShape()
        surfaces[region] = surface
        faces[region] = face
        for section, profile in zip(
            request["sections"], profiles[region], strict=True
        ):
            surface_holds[region].append(
                {
                    "section_idx": section["idx"],
                    **_curve_distance_summary(
                        profile.discretize(Number=PROFILE_SAMPLES), face
                    ),
                }
            )

    # 3. 尖后缘两侧只在 LE/TE 承诺 C0；钝后缘 full-wrap 曲面没有 LE 接缝，
    #    仅在上下 TE 之间增加使用最终曲面精确边的 ruled closure。
    shell_faces = list(faces.values())
    trailing_closure = None
    if topology == "blunt":
        # closure 必须复用 full-wrap 曲面的精确 TE 边，不能用原始 guide 另造
        # 一条仅近似重合的缝。
        trailing_upper_edge, trailing_lower_edge = _find_distinct_boundary_edges(
            faces["full"],
            guides["trailing_upper"],
            guides["trailing_lower"],
        )
        trailing_closure = Part.makeRuledSurface(
            trailing_upper_edge,
            trailing_lower_edge,
        )
        shell_faces.append(trailing_closure)
        caps = [
            _make_open_profile_cap(faces["full"], profiles["full"][index])
            for index in (0, -1)
        ]
    else:
        caps = [
            _make_cap(
                faces["upper"],
                faces["lower"],
                profiles["upper"][index],
                profiles["lower"][index],
            )
            for index in (0, -1)
        ]
    shell_faces.extend(caps)
    shell = Part.makeShell(shell_faces)
    shell.sewShape()
    solid = Part.makeSolid(shell)
    if not solid.isValid() or not solid.isClosed() or len(solid.Solids) != 1:
        diagnostic = {
            "gordon_faces": {
                region: _shape_state(face) for region, face in faces.items()
            },
            "caps": [_shape_state(cap) for cap in caps],
            "trailing_closure": (
                _shape_state(trailing_closure) if trailing_closure else None
            ),
            "shell": _shape_state(shell),
            "shell_free_edges": _free_edge_states(shell),
            "solid": _shape_state(solid),
        }
        failed_path = (
            Path(os.environ["AUTOBLADE_PROTOTYPE_OUTPUT_DIR"])
            / "failed-shell.brep"
        )
        Part.makeCompound(shell_faces).exportBrep(str(failed_path))
        raise ValueError(
            "Gordon result is not one valid closed solid: "
            + json.dumps(diagnostic, sort_keys=True)
        )

    guide_hold = {}
    for name, curve in guides.items():
        points = curve.discretize(Number=GUIDE_SAMPLES)
        target_faces = (
            faces["full"]
            if topology == "blunt"
            else faces["upper"]
            if name == "trailing_upper"
            else faces["lower"]
            if name == "trailing_lower"
            else Part.makeCompound(list(faces.values()))
        )
        guide_hold[name] = _curve_distance_summary(points, target_faces)

    continuity = {
        side: {
            "chordwise_u": _continuity(surface, "u"),
            "spanwise_v": _continuity(surface, "v"),
        }
        for side, surface in surfaces.items()
    }
    for region, measured in continuity.items():
        if measured["spanwise_v"]["minimum_interior_continuity_order"] < 2:
            raise ValueError(
                f"{region} Gordon surface does not meet interior C2."
            )

    network_shape = Part.makeCompound(
        [profile.toShape() for region in profiles.values() for profile in region]
        + [guide.toShape() for guide in guides.values()]
    )
    network_scale_mm = network_shape.BoundBox.DiagonalLength
    hold_limit_mm = max(
        network_scale_mm * options["relative_network_tolerance"],
        1e-7,
    )
    maximum_section_hold_mm = max(
        item["max_mm"]
        for region in surface_holds.values()
        for item in region
    )
    maximum_guide_hold_mm = max(item["max_mm"] for item in guide_hold.values())

    measurements = {
        "parameterization": {
            "profile": (
                "normalized-cumulative-arc-per-sharp-side"
                if topology == "sharp"
                else "normalized-cumulative-arc-per-half-with-leading-at-0.5"
            ),
            "span": "normalized-cumulative-mean-of-leading-and-two-trailing-guides",
            "span_parameters": span_parameters,
        },
        "profile_curve_fit": profile_fit,
        "surface_section_hold": surface_holds,
        "guide_hold": guide_hold,
        "network_quality": {
            "network_scale_mm": network_scale_mm,
            "relative_tolerance": options["relative_network_tolerance"],
            "hold_limit_mm": hold_limit_mm,
            "maximum_section_hold_mm": maximum_section_hold_mm,
            "maximum_guide_hold_mm": maximum_guide_hold_mm,
        },
        "continuity": continuity,
        "solid": {
            "valid": solid.isValid(),
            "closed": solid.isClosed(),
            "solids": len(solid.Solids),
            "volume_mm3": solid.Volume,
            "center_of_mass_mm": list(solid.CenterOfMass),
            "bounding_box_mm": {
                "x_min": solid.BoundBox.XMin,
                "x_max": solid.BoundBox.XMax,
                "y_min": solid.BoundBox.YMin,
                "y_max": solid.BoundBox.YMax,
                "z_min": solid.BoundBox.ZMin,
                "z_max": solid.BoundBox.ZMax,
            },
        },
    }
    audit_shapes = Part.makeCompound(
        [profile.toShape() for side in profiles.values() for profile in side]
        + [guide.toShape() for guide in guides.values()]
    )
    return solid, measurements, audit_shapes


def _validate_geometry_quality(measurements: dict[str, Any]) -> None:
    """把 profile/guide hold 从报告项提升为阶段 2 的强制数值 gate。"""
    quality = measurements["network_quality"]
    failures = {
        name: quality[name]
        for name in ("maximum_section_hold_mm", "maximum_guide_hold_mm")
        if quality[name] > quality["hold_limit_mm"]
    }
    if failures:
        raise ValueError(
            "Gordon network hold exceeds the scale-relative tolerance: "
            + json.dumps(
                {"limit_mm": quality["hold_limit_mm"], **failures},
                sort_keys=True,
            )
        )


def _save_and_verify(
    request: dict[str, Any],
    solid: Any,
    measurements: dict[str, Any],
    audit_shapes: Any,
    output_dir: Path,
    dependency_digest: str,
) -> dict[str, Any]:
    artifacts = request["artifacts"]
    native_path = output_dir / artifacts["native_model"]
    step_path = output_dir / artifacts["step"]
    digest = request_sha256(request)

    doc = App.newDocument("AutoBladeGordonPrototype")
    # FreeCAD 1.1.3 不公开可直接实例化的 ``App::Feature``；使用空 Shape 的
    # ``Part::Feature`` 只承载标准属性，不引入 FeaturePython 或运行时代理。
    traceability = doc.addObject("Part::Feature", "Traceability")
    for name in (
        "RequestSHA256",
        "Algorithm",
        "CurvesWBCommit",
        "CurvesWBVersion",
        "DependencyFingerprintSHA256",
        "LengthUnit",
        "RebuildSemantics",
        "ContinuityContract",
        "RebuildRequestJson",
    ):
        traceability.addProperty("App::PropertyString", name)
    traceability.RequestSHA256 = digest
    traceability.Algorithm = request["modeling"]["algorithm"]
    traceability.CurvesWBCommit = CURVESWB_COMMIT
    traceability.CurvesWBVersion = CURVESWB_VERSION
    traceability.DependencyFingerprintSHA256 = dependency_digest
    traceability.LengthUnit = request["length_unit"]
    traceability.RebuildSemantics = request["modeling"]["rebuild_semantics"]
    traceability.ContinuityContract = request["modeling"]["continuity_contract"]
    traceability.RebuildRequestJson = canonical_json(request)

    audit = doc.addObject("Part::Feature", "InputCurveNetwork")
    audit.Shape = audit_shapes
    audit.Visibility = False
    blade = doc.addObject("Part::Feature", "BladeSolid")
    blade.Shape = solid
    doc.recompute()
    doc.saveAs(str(native_path))
    App.closeDocument(doc.Name)

    # 4. 关闭重开后核对静态 Shape 和嵌入输入；重算声明只指外部固定 Runner。
    reopened = App.openDocument(str(native_path))
    reopened.recompute(None, True, True)
    reopened_blade = reopened.getObject("BladeSolid")
    reopened_traceability = reopened.getObject("Traceability")
    if (
        reopened_blade is None
        or not reopened_blade.Shape.isValid()
        or not reopened_blade.Shape.isClosed()
        or len(reopened_blade.Shape.Solids) != 1
    ):
        raise ValueError("Reopened FCStd does not contain one valid closed solid.")
    embedded = validate_request(json.loads(reopened_traceability.RebuildRequestJson))
    if request_sha256(embedded) != digest:
        raise ValueError("Reopened FCStd embedded request digest changed.")

    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Part/STEP").SetString(
        "Scheme", request["modeling"]["step_schema"]
    )
    Import.export([reopened_blade], str(step_path))
    step_text = step_path.read_text(encoding="utf-8", errors="replace")
    schema_start = step_text.index("FILE_SCHEMA")
    schema_end = step_text.index("ENDSEC;", schema_start)
    schema_declaration = step_text[schema_start:schema_end]
    if "AP242" not in schema_declaration.upper():
        raise ValueError(f"Unexpected STEP schema: {schema_declaration}")
    imported = Part.read(str(step_path))
    if not imported.isValid() or len(imported.Solids) != 1:
        raise ValueError("STEP reopen did not produce one valid solid.")
    measurements["reopen"] = {
        "fcstd_valid": reopened_blade.Shape.isValid(),
        "fcstd_closed": reopened_blade.Shape.isClosed(),
        "fcstd_solids": len(reopened_blade.Shape.Solids),
        "embedded_request_sha256": digest,
        "rebuild_semantics": request["modeling"]["rebuild_semantics"],
        "step_schema_declaration": schema_declaration,
        "step_valid": imported.isValid(),
        "step_solids": len(imported.Solids),
        "step_volume_mm3": imported.Volume,
        "step_center_of_mass_mm": list(imported.Solids[0].CenterOfMass),
    }
    App.closeDocument(reopened.Name)
    return {
        "native_model": str(native_path),
        "native_model_sha256": hashlib.sha256(native_path.read_bytes()).hexdigest(),
        "step": str(step_path),
        "step_sha256": hashlib.sha256(step_path.read_bytes()).hexdigest(),
    }


def run() -> None:
    output_dir = Path(os.environ["AUTOBLADE_PROTOTYPE_OUTPUT_DIR"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "status": "failed",
        "freecad_version": list(App.Version()),
        "curveswb_commit": CURVESWB_COMMIT,
        "curveswb_version": CURVESWB_VERSION,
    }
    try:
        _, dependency_digest = _configure_curveswb()
        request, request_source = _load_request()
        result["dependency_fingerprint_sha256"] = dependency_digest
        result["request_sha256"] = request_sha256(request)
        result["request_source"] = request_source
        solid, measurements, audit_shapes = _build_geometry(request)
        result["measurements"] = measurements
        _validate_geometry_quality(measurements)
        result["artifacts"] = _save_and_verify(
            request,
            solid,
            measurements,
            audit_shapes,
            output_dir,
            dependency_digest,
        )
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


# FreeCADCmd 通过执行脚本加载 Runner；无条件调用可避免其非标准 __name__ 语义。
run()
