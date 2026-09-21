"""FreeCAD 子进程中的只读几何测量，单位统一为 mm。

全局样本来自固定 deflection 的曲面网格顶点，距离投影到对方裁剪曲面集合。
有限样本 max 不是连续 Hausdorff 上界，RMS 按点计权而不是按面积计权。
固定站位由已批准 manifest 给出，不随当前模型峰值移动；拓扑编号不参与比较。
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import resource
import sys
import time
import traceback

import FreeCAD as App
import Part


sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture import DIRECTIONS, load_fixture, sha256, step_data, validate_measurements
from candidate_contract import load_candidate


def subset(points, limit):
    """保持点序的确定性等索引抽样，不构造可能离开曲面的网格重心。"""
    if len(points) <= limit:
        return points
    return [points[round(i * (len(points) - 1) / (limit - 1))] for i in range(limit)]


def surface_points(shape, sampling):
    return subset(
        shape.tessellate(sampling["deflection_mm"])[0], sampling["surface_samples"]
    )


def section_points(shape, sampling):
    """按边长分配样本，减少短边数量对 RMS 权重的影响。"""
    if not shape.Edges or shape.Length <= 0:
        raise ValueError("Section has no measurable edges.")
    points = []
    for edge in shape.Edges:
        count = max(3, round(sampling["section_samples"] * edge.Length / shape.Length))
        points.extend(edge.discretize(Number=count))
    return subset(points, sampling["section_samples"])


def distance(points, target):
    if not points:
        raise ValueError("No distance samples.")
    rows = []
    for point in points:
        value, pairs, _ = Part.Vertex(point).distToShape(target)
        if not math.isfinite(value) or value < 0:
            raise ValueError("Invalid geometric distance.")
        rows.append((value, list(point), list(pairs[0][1])))
    worst = max(rows, key=lambda row: row[0])
    return {
        "samples": len(rows),
        "max_mm": worst[0],
        "rms_mm": math.sqrt(sum(row[0] ** 2 for row in rows) / len(rows)),
        "worst_source_mm": worst[1],
        "worst_target_mm": worst[2],
    }


def properties(shape):
    """沿用获批测量器的 OCCT 默认体积积分；不以面数/边数作为几何判据。"""
    if not shape.isValid() or not shape.isClosed() or len(shape.Solids) != 1:
        raise ValueError("Expected one valid closed solid.")
    box = shape.BoundBox
    return {
        "valid": True,
        "closed": True,
        "solids": 1,
        "volume_mm3": shape.Volume,
        "center_of_mass_mm": list(shape.Solids[0].CenterOfMass),
        "bounding_box_mm": [box.XMin, box.XMax, box.YMin, box.YMax, box.ZMin, box.ZMax],
    }


def compare(candidate, reference, candidate_properties, reference_properties, sampling):
    """双向投影目标是 Faces 集合，避免实体内部点被错误地视为零距离。"""
    return {
        "volume_relative": abs(
            candidate_properties["volume_mm3"] / reference_properties["volume_mm3"] - 1
        ),
        "centroid_max_mm": max(
            abs(a - b)
            for a, b in zip(
                candidate_properties["center_of_mass_mm"],
                reference_properties["center_of_mass_mm"],
                strict=True,
            )
        ),
        "bbox_max_mm": max(
            abs(a - b)
            for a, b in zip(
                candidate_properties["bounding_box_mm"],
                reference_properties["bounding_box_mm"],
                strict=True,
            )
        ),
        "surface": {
            DIRECTIONS[0]: distance(
                surface_points(candidate, sampling), Part.makeCompound(reference.Faces)
            ),
            DIRECTIONS[1]: distance(
                surface_points(reference, sampling), Part.makeCompound(candidate.Faces)
            ),
        },
    }


def section_state(section):
    groups = Part.sortEdges(section.Edges)
    closed = 0
    for group in groups:
        try:
            closed += int(Part.Wire(group).isClosed())
        except Exception:
            # 缺边/无法组 wire 必须体现在 coverage，不能把“有边”当成完整截面。
            pass
    return {
        "connected_groups": len(groups),
        "closed_groups": closed,
        "length_mm": section.Length,
    }


def station(candidate, reference, plan, sampling):
    # 平面覆盖当前两模型的共同 bbox；不把原型 4000 mm 的尺寸假设带入通用工具。
    box = candidate.BoundBox
    box.add(reference.BoundBox)
    extent = max(box.DiagonalLength * 2, 1)
    attempts = []
    initial = None
    complete = False
    for offset in sampling["retry_offsets_mm"]:
        plane = Part.makePlane(extent, extent, App.Vector(-extent / 2, -extent / 2, 0))
        plane.rotate(App.Vector(), App.Vector(0, 1, 0), 90)
        plane.translate(App.Vector(plan["x_mm"] + offset, box.Center.y, box.Center.z))
        left, right = candidate.section(plane), reference.section(plane)
        if initial is None:
            initial = (left, right)
        states = [section_state(shape) for shape in (left, right)]
        complete = all(
            state["connected_groups"] == state["closed_groups"] == 1 for state in states
        )
        attempts.append(
            {
                "offset_mm": offset,
                "candidate": states[0],
                "reference": states[1],
                "complete": complete,
            }
        )
        if complete:
            break
    row = {
        "requested_x_mm": plan["x_mm"],
        "plane_offset_mm": offset,
        "complete": complete,
        "attempts": attempts,
    }
    if complete:
        row["section"] = {
            DIRECTIONS[0]: distance(section_points(left, sampling), right),
            DIRECTIONS[1]: distance(section_points(right, sampling), left),
        }
    else:
        # 重试仍不完整时回到原始站位，测量全部返回样本到完整对方曲面的距离；
        # 明确保留双方样本数，不能把残缺截面反向距离混进固定截面的统计。
        left, right = initial
        row["surface_diagnostic"] = {
            DIRECTIONS[0]: distance(
                section_points(left, sampling), Part.makeCompound(reference.Faces)
            ),
            DIRECTIONS[1]: distance(
                section_points(right, sampling), Part.makeCompound(candidate.Faces)
            ),
        }
    return row


def run():
    job = json.loads(
        Path(os.environ["AUTOBLADE_GOLDEN_JOB"]).read_text(encoding="utf-8")
    )
    output = Path(job["output"])
    started = time.monotonic()
    report = {
        "schema": "autoblade.geometry-measurement/v1",
        "status": "measurement_error",
        "decision_policy": "human_only",
        "usability": "requires_human_judgment",
        "units": {"length": "mm", "volume": "mm^3", "relative_difference": "ratio"},
    }
    document = None
    try:
        # 1. 子进程再次校验基线字节，并严格核对获批内核环境。
        case = Path(job["case"])
        candidate = job.get("candidate", False)
        manifest = load_candidate(case) if candidate else load_fixture(case)
        manifest_name = "candidate.json" if candidate else "manifest.json"
        report["scope"] = "unapproved_candidate" if candidate else "approved_golden"
        report["case_id"] = manifest["case_id"]
        report["sampling"] = manifest["sampling"]
        report["manifest_sha256"] = sha256((case / manifest_name).read_bytes())
        report["baseline_sha256"] = sha256(
            (case / manifest["baseline"]["step"]).read_bytes()
        )
        report["freecad_version"] = ".".join(App.Version()[:3])
        report["occt_version"] = Part.OCC_VERSION
        for key in ("freecad_version", "occt_version"):
            if report[key] != manifest["environment"][key]:
                raise ValueError(f"Uncertified golden environment: {key}={report[key]}")
        baseline_path = case / manifest["baseline"]["step"]
        catia = Part.read(str(baseline_path))
        catia_properties = properties(catia)
        # 可选原始字节审计只用于首次清理，不是日常回归的本机路径依赖。
        if job.get("original"):
            original_path = Path(job["original"])
            original_bytes = original_path.read_bytes()
            if sha256(original_bytes) != manifest["authorization"]["original_sha256"]:
                raise ValueError("Unapproved original STEP.")
            original_properties = properties(Part.read(str(original_path)))
            if (
                step_data(original_bytes) != step_data(baseline_path.read_bytes())
                or original_properties != catia_properties
            ):
                raise ValueError("STEP sanitization changed DATA or reopened geometry.")
            report["sanitization_audit"] = {
                "data_bytes_equal": True,
                "reopened_properties_equal": True,
                "original_sha256": sha256(original_bytes),
                "sanitized_sha256": sha256(baseline_path.read_bytes()),
            }

        # 2. FCStd 和 STEP 分别重开，并检查请求身份，防止拿无关旧模型通过门禁。
        native_path, step_path = Path(job["native"]), Path(job["step"])
        document = App.openDocument(str(native_path))
        trace = document.getObject("Traceability")
        blade = document.getObject("BladeSolid")
        if (
            trace is None
            or blade is None
            or trace.RequestSHA256 != job["request_sha256"]
        ):
            raise ValueError("Native model does not match the fixture request.")
        native, step = blade.Shape, Part.read(str(step_path))
        report["artifacts"] = {
            "native_sha256": sha256(native_path.read_bytes()),
            "step_sha256": sha256(step_path.read_bytes()),
            "request_sha256": trace.RequestSHA256,
        }
        props = report["properties"] = {
            "native": properties(native),
            "step": properties(step),
            "catia": catia_properties,
        }
        sampling = manifest["sampling"]
        # 3. 候选和公开参照均只报告数值。较大误差不改变报告状态，适用性归人类。
        print("Measuring native-to-STEP exchange", flush=True)
        report["exchange"] = compare(
            native, step, props["native"], props["step"], sampling
        )
        print("Measuring cross-backend surfaces", flush=True)
        report["cross_backend"] = compare(
            native, catia, props["native"], props["catia"], sampling
        )
        report["stations"] = []
        for plan in sampling["stations"]:
            row = station(native, catia, plan, sampling)
            report["stations"].append(row)
            print(
                f"Station {plan['x_mm']:.9f} mm: complete={row['complete']}", flush=True
            )
        report["coverage"] = validate_measurements(report, manifest)
        report["status"] = "measured_candidate" if candidate else "measured"
        report["comparison_policy"] = "measurements_only_user_judgment"
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if document is not None:
            App.closeDocument(document.Name)
        report["elapsed_seconds"] = time.monotonic() - started
        report["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        (output / "result.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    key: report.get(key)
                    for key in ("status", "error", "elapsed_seconds")
                }
            ),
            flush=True,
        )


# FreeCADCmd 的脚本加载方式不保证 __name__ == '__main__'。
run()
