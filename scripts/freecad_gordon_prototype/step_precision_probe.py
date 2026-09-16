"""比较 OCCT STEP writer precision 模式的阶段 2 只读探针。

由 ``FreeCADCmd`` 直接执行：读取已有 FCStd 的 ``BladeSolid``，分别以平均 BRep
容差、显式 ``1e-7 mm`` 和显式 ``1e-6 mm`` 导出 STEP。探针不重建几何，也不
修改输入 FCStd；输出只用于提出待批准的产品 precision 契约。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import resource
import time
from pathlib import Path
from typing import Any

import FreeCAD as App
import Import
import Part


SCHEMA_PATTERN = re.compile(r"FILE_SCHEMA\(.*?ENDSEC;", re.DOTALL)
UNCERTAINTY_PATTERN = re.compile(
    r"UNCERTAINTY_MEASURE_WITH_UNIT\(LENGTH_MEASURE\(([^)]+)\)"
)
SAMPLE_LIMIT = 100


def _sample_points(shape: Any) -> list[Any]:
    """以固定 deflection 取得确定性有限曲面样本，并限制距离计算成本。"""
    points, _ = shape.tessellate(0.5)
    if len(points) <= SAMPLE_LIMIT:
        return points
    return [
        points[round(index * (len(points) - 1) / (SAMPLE_LIMIT - 1))]
        for index in range(SAMPLE_LIMIT)
    ]


def _distance_summary(points: list[Any], shape: Any) -> dict[str, float | int]:
    distances = [Part.Vertex(point).distToShape(shape)[0] for point in points]
    return {
        "samples": len(distances),
        "max_mm": max(distances),
        "rms_mm": math.sqrt(
            sum(distance * distance for distance in distances) / len(distances)
        ),
    }


def _export_case(
    blade: Any,
    native_points: list[Any],
    output_dir: Path,
    *,
    name: str,
    precision_mode: int,
    precision_mm: float | None,
) -> dict[str, Any]:
    """导出一个独立 STEP，并记录文件声明、几何往返与 mass properties。"""
    Part.setStaticValue("write.step.schema", "AP242DIS")
    Part.setStaticValue("write.step.unit", "MM")
    Part.setStaticValue("xstep.cascade.unit", "MM")
    Part.setStaticValue("write.surfacecurve.mode", 1)
    Part.setStaticValue("write.precision.mode", precision_mode)
    if precision_mm is not None:
        Part.setStaticValue("write.precision.val", precision_mm)

    path = output_dir / f"{name}.stp"
    if path.exists():
        raise ValueError(f"Probe output already exists: {path}")
    Import.export([blade], str(path))
    step_text = path.read_text(encoding="utf-8", errors="replace")
    imported = Part.read(str(path))
    if not imported.isValid() or len(imported.Solids) != 1:
        raise ValueError(f"STEP precision probe did not reopen as one solid: {name}")
    imported_points = _sample_points(imported)
    schema_match = SCHEMA_PATTERN.search(step_text)
    uncertainty_match = UNCERTAINTY_PATTERN.search(step_text)
    if schema_match is None or uncertainty_match is None:
        raise ValueError(f"STEP metadata is incomplete: {name}")
    return {
        "precision_mode": precision_mode,
        "requested_precision_mm": precision_mm,
        "declared_uncertainty_mm": float(uncertainty_match.group(1)),
        "schema_declaration": schema_match.group(0),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "valid": imported.isValid(),
        "solids": len(imported.Solids),
        "volume_mm3": imported.Volume,
        "center_of_mass_mm": list(imported.Solids[0].CenterOfMass),
        "native_to_step": _distance_summary(native_points, imported),
        "step_to_native": _distance_summary(imported_points, blade.Shape),
    }


def run() -> None:
    source_value = os.environ.get("AUTOBLADE_STEP_PROBE_SOURCE")
    output_value = os.environ.get("AUTOBLADE_STEP_PROBE_OUTPUT")
    if not source_value or not output_value:
        raise ValueError(
            "AUTOBLADE_STEP_PROBE_SOURCE and AUTOBLADE_STEP_PROBE_OUTPUT are required."
        )
    source_path = Path(source_value).resolve(strict=True)
    output_dir = Path(output_value).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    if result_path.exists():
        raise ValueError(f"Probe result already exists: {result_path}")

    started = time.monotonic()
    document = App.openDocument(str(source_path))
    try:
        blade = document.getObject("BladeSolid")
        if blade is None or not blade.Shape.isValid() or len(blade.Shape.Solids) != 1:
            raise ValueError("Source FCStd does not contain one valid BladeSolid.")
        native_points = _sample_points(blade.Shape)
        result = {
            "source_fcstd": str(source_path),
            "source_fcstd_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "freecad_version": list(App.Version()),
            "native": {
                "valid": blade.Shape.isValid(),
                "closed": blade.Shape.isClosed(),
                "solids": len(blade.Shape.Solids),
                "volume_mm3": blade.Shape.Volume,
                "center_of_mass_mm": list(blade.Shape.CenterOfMass),
                "tolerance_min_mm": blade.Shape.getTolerance(-1),
                "tolerance_average_mm": blade.Shape.getTolerance(0),
                "tolerance_max_mm": blade.Shape.getTolerance(1),
                "surface_samples": len(native_points),
            },
            "cases": {},
        }
        for name, mode, value in (
            ("average", 0, None),
            ("session-1e-7-mm", 2, 1e-7),
            ("session-1e-6-mm", 2, 1e-6),
        ):
            result["cases"][name] = _export_case(
                blade,
                native_points,
                output_dir,
                name=name,
                precision_mode=mode,
                precision_mm=value,
            )
        result["elapsed_seconds"] = time.monotonic() - started
        result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        App.closeDocument(document.Name)


# FreeCADCmd 直接执行脚本；保持与主 Runner 相同的无入口守卫约束。
run()
