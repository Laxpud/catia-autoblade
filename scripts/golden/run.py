"""从公开夹具重新建模并执行数值回归；必须显式运行，不进入默认 pytest。

读取项目固定 backend 和 CurvesWB 闭包，不依赖用户配置。结果只写入新 output
目录，既不重写黄金 STEP，也不提供自动更新基线或放宽阈值的选项。
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import math
import os
from pathlib import Path
import time

from autoblade.adapters.cad.freecad.adapter import FreeCADBackend
from autoblade.adapters.cad.freecad.process import run_process
from autoblade.adapters.cad.freecad.protocol import request_sha256
from autoblade.adapters.cad.freecad.request import build_request
from autoblade.core.backend import BackendName
from autoblade.core.input_plan import build_blade_input_plan
from autoblade.core.jobs import BladeBuildJob

from ..smoke_real_freecad import instances, wait_instances
from .fixture import DEFAULT_CASE, load_fixture, sha256, validate_measurements
from .report import write_error_report


def measure_artifacts(
    *,
    case: Path,
    output: Path,
    native: Path,
    step: Path,
    digest: str,
    timeout: float,
    original: Path | None = None,
    candidate: bool = False,
) -> dict:
    """在独占子进程中测量已有制品；黄金与待批准候选使用明确不同的状态。"""
    measurement = {
        "case": str(case),
        "output": str(output),
        "native": str(native),
        "step": str(step),
        "request_sha256": digest,
        "original": str(original) if original else None,
        "candidate": candidate,
    }
    job_path = output / "measurement.json"
    job_path.write_text(json.dumps(measurement, indent=2) + "\n", encoding="utf-8")
    runner = Path(__file__).with_name("measure.py").resolve()
    command = [
        "flatpak",
        "run",
        "--die-with-parent",
        "--command=FreeCADCmd",
        f"--filesystem={output}",
        f"--filesystem={case}:ro",
        f"--filesystem={native.parent}:ro",
        f"--filesystem={runner.parent}:ro",
    ]
    if original:
        command.append(f"--filesystem={original.parent}:ro")
    command += [
        "org.freecad.FreeCAD",
        "-u",
        str(output / "user.cfg"),
        "-s",
        str(output / "system.cfg"),
        str(runner),
    ]
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME"} and not key.startswith("AUTOBLADE_")
    }
    env.update(
        {
            "AUTOBLADE_GOLDEN_JOB": str(job_path),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    print("Measuring golden geometry", flush=True)
    code, stdout, stderr = run_process(command, env=env, timeout=timeout)
    (output / "measure.log").write_text(stdout + "\n" + stderr, encoding="utf-8")
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    if code != 0:
        raise RuntimeError(
            f"FreeCAD measurement exited with {code}; see {output / 'measure.log'}"
        )
    if result["status"] in {"measured", "measured_candidate"}:
        write_error_report(result, output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-original", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be finite and positive")
    case = args.case.resolve(strict=True)
    manifest = load_fixture(case)
    output = args.output.resolve()
    if output.is_relative_to(case):
        parser.error("--output must be outside the golden fixture")
    sections = case / manifest["input"]["sections"]
    airfoils = case / "input/airfoils"
    plan = build_blade_input_plan(sections, airfoils, manifest["input"]["airfoil"])
    if (
        len(plan.sections) != manifest["input"]["section_count"]
        or [len(item.points) for item in plan.airfoils]
        != manifest["input"]["point_counts"]
        or plan.is_sharp != (manifest["input"]["trailing_edge"] == "sharp")
    ):
        raise ValueError("Parsed input differs from the golden fixture contract.")
    original = args.audit_original.resolve(strict=True) if args.audit_original else None
    if (
        original
        and sha256(original.read_bytes())
        != manifest["authorization"]["original_sha256"]
    ):
        raise ValueError("Original STEP does not match the approved SHA-256.")
    output.mkdir(parents=True, exist_ok=False)
    before = instances()
    job = BladeBuildJob(
        mode=plan.mode,
        airfoil_filename=manifest["input"]["airfoil"],
        blade_sections_filename=sections.name,
        airfoil_dir=airfoils,
        blade_sections_dir=sections.parent,
        output_dir=output / "model",
        output_name="blade",
        input_plan=plan,
        backend=BackendName.FREECAD,
        timeout_seconds=args.timeout_seconds,
        verbose=True,
    )
    print(f"Building golden case: {manifest['case_id']}", flush=True)
    started = time.monotonic()
    with (
        (output / "build.log").open("x", encoding="utf-8") as log,
        redirect_stdout(log),
    ):
        FreeCADBackend().build(job)
    build_seconds = time.monotonic() - started
    wait_instances(before)
    native, step = job.output_paths
    request = build_request(plan, native_model=native.name, step=step.name)
    result = measure_artifacts(
        case=case,
        output=output,
        native=native,
        step=step,
        digest=request_sha256(request),
        timeout=args.timeout_seconds,
        original=original,
    )
    wait_instances(before)
    if result["status"] != "measured" or result["manifest_sha256"] != sha256(
        (case / "manifest.json").read_bytes()
    ):
        raise RuntimeError(f"Golden measurement failed; see {output / 'result.json'}")
    coverage = validate_measurements(result, manifest)
    summary = {
        "case_id": manifest["case_id"],
        "build_seconds": build_seconds,
        "measurement_seconds": result["elapsed_seconds"],
        "measurement_peak_rss_kib": result["peak_rss_kib"],
        "instances_before": sorted(before),
        "instances_after": sorted(instances()),
        "status": "measured",
        "decision_policy": "human_only",
        "usability": "requires_human_judgment",
        "coverage": coverage,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
