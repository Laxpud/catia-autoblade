"""显式生成、建模和测量黄金矩阵候选；不修改任何已批准夹具。

合成翼型是本项目直接定义的数学测试几何，不冒充 NACA 或其他实测翼型。
所有 CSV 坐标采用 m，TE→LE→TE 点序；保留公式、采样和仿射变换参数以供复查。
CATIA/FreeCAD 建模命令必须由维护者显式调用，默认 pytest 只测试纯输入与契约。
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import csv
import json
import math
from pathlib import Path
import shutil
import time

import autoblade
from autoblade.adapters.cad.factory import get_backend
from autoblade.core.backend import BackendName
from autoblade.core.geometry import transform_point
from autoblade.core.input_plan import build_blade_input_plan
from autoblade.core.jobs import BladeBuildJob

from ..inspect_catia_artifact import REQUIRED_FEATURES, inspect_artifact
from ..smoke_real_freecad import instances, wait_instances
from .candidate_contract import (
    CANDIDATE_SCHEMA,
    PENDING,
    affine_residual,
    load_candidate,
)
from .fixture import DEFAULT_CASE, ROOT, fixture_path, load_fixture, sha256
from .run import measure_artifacts


SECTION_HEADER = (
    "idx",
    "scale/m",
    "translate_x/m",
    "translate_y/m",
    "translate_z/m",
    "rotate/deg",
)
# 每行是 idx、弦长 m、位置 x/y/z m、绕 X 轴旋转 deg；根部包含精确零平移。
SECTIONS = (
    (1, 0.12, 0.0, 0.0, 0.0, 8.0),
    (2, 0.115, 0.125, 0.005, 0.001, 5.0),
    (3, 0.105, 0.250, 0.009, 0.003, 2.0),
    (4, 0.095, 0.375, 0.012, 0.006, -1.0),
    (5, 0.085, 0.500, 0.015, 0.010, -4.0),
)
TRANSFORMS = {
    "affine-05": {
        "scale": 0.5,
        "rotation_x_deg": -23.0,
        "translation_m": [-0.05, 0.04, -0.02],
    },
    "affine-17": {
        "scale": 1.7,
        "rotation_x_deg": 37.0,
        "translation_m": [0.2, -0.1, 0.3],
    },
    "affine-25": {
        "scale": 2.5,
        "rotation_x_deg": -41.0,
        "translation_m": [-0.1, 0.2, -0.05],
    },
}


def profile_points(
    count: int, *, amplitude: float = 0.156, camber: float = 0.0, gap: float = 0.0
) -> list[tuple[float, float, float]]:
    """用余弦弦向采样生成归一化翼型，返回 shape=(count, 3) 的米制点云。

    半厚度 h(y)=amplitude*sqrt(y)*(1-y)+gap*y/2，中线 c(y)=camber*y*(1-y)。
    这是专为回归定义的圆滑前缘/显式尖钝后缘曲线。gap=0 时首尾精确相等；
    gap>0 保持两后缘不同，禁止用几何容差自动合并。偶数点数允许上下侧点数相差1。
    """
    if type(count) is not int or count < 5 or amplitude <= 0 or gap < 0:
        raise ValueError("Invalid synthetic profile parameters.")
    if not all(math.isfinite(value) for value in (amplitude, camber, gap)):
        raise ValueError("Synthetic profile parameters must be finite.")
    upper = (count + 1) // 2
    lower = count - upper + 1
    points = []
    for sign, indices, total in (
        (1, range(upper - 1, -1, -1), upper),
        (-1, range(1, lower), lower),
    ):
        for index in indices:
            y = (1 - math.cos(math.pi * index / (total - 1))) / 2
            h = amplitude * math.sqrt(y) * (1 - y) + gap * y / 2
            z = camber * y * (1 - y) + sign * h
            points.append((0.0, y, z))
    return points


def write_csv(path: Path, header, rows) -> None:
    """固定 LF 和 15 位有效数字，保存显式数值文件而不让 CAD 重采样输入。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(
                [
                    format(value, ".15g") if isinstance(value, float) else value
                    for value in row
                ]
            )


def transformed_sections(transform: dict) -> list[tuple]:
    rows = []
    for index, chord, x, y, z, rotation in SECTIONS:
        position = transform_point(
            x,
            y,
            z,
            transform["rotation_x_deg"],
            transform["scale"],
            *transform["translation_m"],
        )
        rows.append(
            (
                index,
                chord * transform["scale"],
                *position,
                rotation + transform["rotation_x_deg"],
            )
        )
    return rows


def prepare(output: Path) -> None:
    """生成七个可复查候选，输出根目录必须不存在，避免覆盖已获审阅的字节。"""
    approved = load_fixture(DEFAULT_CASE)
    output.mkdir(parents=True, exist_ok=False)
    recipes = {
        "single-sharp": [(121, 0.156, 0.0, 0.0)],
        "single-blunt": [(121, 0.156, 0.0, 0.004)],
        "multi-blunt": [
            (121, 0.156, 0.0, 0.004),
            (153, 0.13, 0.015, 0.003),
            (181, 0.104, 0.025, 0.002),
        ],
        **{name: [(121, 0.156, 0.0, 0.0)] for name in TRANSFORMS},
        "dense-1000": [(1000, 0.156, 0.0, 0.0)],
    }
    for name, profiles in recipes.items():
        case = output / name
        names = []
        for index, (count, amplitude, camber, gap) in enumerate(profiles, 1):
            filename = f"synthetic-{index}.csv"
            names.append(filename)
            write_csv(
                case / "input/airfoils" / filename,
                ("x", "y", "z"),
                profile_points(count, amplitude=amplitude, camber=camber, gap=gap),
            )
        rows = (
            transformed_sections(TRANSFORMS[name])
            if name in TRANSFORMS
            else list(SECTIONS)
        )
        if len(profiles) > 1:
            rows = [
                (*row, names[profile])
                for row, profile in zip(rows, (0, 0, 1, 2, 2), strict=True)
            ]
        write_csv(
            case / "input/blade_sections.csv",
            (*SECTION_HEADER, "airfoil") if len(profiles) > 1 else SECTION_HEADER,
            rows,
        )
        shutil.copyfile(ROOT / "LICENSE", case / "LICENSE.md")
        # 初始网格在建模之前固定，每相邻输入截面取 5%..95%，再补内部输入站位。
        # 这样单翼型案例也有截面约束，不能仅沿翼型切换区采样。
        positions = [row[2] * 1000 for row in rows]
        stations = sorted(
            set(
                positions[1:-1]
                + [
                    left + (right - left) * i / 20
                    for left, right in zip(positions, positions[1:])
                    for i in range(1, 20)
                ]
            )
        )
        data = {
            "schema": CANDIDATE_SCHEMA,
            "case_id": name,
            "approval_status": PENDING,
            "role": "performance" if name == "dense-1000" else "golden_candidate",
            "origin": {
                "kind": "project_defined_analytic_geometry",
                "license": "MIT",
                "generator": "scripts/golden/candidates.py",
                "profiles": [
                    dict(
                        zip(
                            ("point_count", "amplitude", "camber", "gap_m"),
                            row,
                            strict=True,
                        )
                    )
                    for row in profiles
                ],
                "transform": TRANSFORMS.get(name),
            },
            "environment": approved["environment"],
            "input": {
                "sections": "input/blade_sections.csv",
                "airfoil": names[0] if len(profiles) == 1 else None,
                "section_count": len(rows),
                "point_counts": [row[0] for row in profiles],
                "trailing_edge": "blunt" if profiles[0][3] else "sharp",
            },
            "baseline": {"step": "catia/blade.stp"},
            "sampling": {
                **approved["sampling"],
                "stations": [{"x_mm": x, "allow_incomplete": False} for x in stations],
                "station_source": "Predeclared 5% grid in every span interval plus internal input stations; no incomplete-station exceptions",
            },
            "comparison_policy": "measurements_only_user_judgment",
            "step_writer": {
                "schema": "AP242DIS",
                "precision_mode": 2,
                "precision_mm": 1e-7,
                "surfacecurve_mode": 1,
                "length_unit": "mm",
            },
            "files": {
                path.relative_to(case).as_posix(): sha256(path.read_bytes())
                for path in sorted(case.rglob("*"))
                if path.is_file()
            },
        }
        (case / "candidate.json").write_text(
            json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    (output / "matrix.json").write_text(
        json.dumps(
            {
                "schema": "autoblade.golden.matrix-candidates/v1",
                "cases": list(recipes),
                "approval_status": PENDING,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def jobs(
    matrix: Path, backend: BackendName, output: Path
) -> list[tuple[Path, dict, BladeBuildJob]]:
    """全矩阵先闭合输入并检查冲突，之后才允许创建第一个 CAD 会话。"""
    specification = json.loads((matrix / "matrix.json").read_text())
    if (
        specification["schema"] != "autoblade.golden.matrix-candidates/v1"
        or specification["approval_status"] != PENDING
        or len(set(specification["cases"])) != len(specification["cases"])
    ):
        raise ValueError("Invalid candidate matrix identity.")
    result = []
    for name in specification["cases"]:
        case = fixture_path(matrix, name)
        data = load_candidate(case, require_catia=False)
        if backend == BackendName.CATIA and data["role"] == "performance":
            continue
        sections = case / data["input"]["sections"]
        airfoils = case / "input/airfoils"
        plan = build_blade_input_plan(sections, airfoils, data["input"]["airfoil"])
        if (
            len(plan.sections) != data["input"]["section_count"]
            or [len(item.points) for item in plan.airfoils]
            != data["input"]["point_counts"]
        ):
            raise ValueError("Candidate input shape differs from its contract.")
        destination = (
            case / "catia" if backend == BackendName.CATIA else output / name / "model"
        )
        if destination.exists():
            raise FileExistsError(
                f"Refusing to overwrite candidate output: {destination}"
            )
        job = BladeBuildJob(
            mode=plan.mode,
            airfoil_filename=data["input"]["airfoil"],
            blade_sections_filename=sections.name,
            airfoil_dir=airfoils,
            blade_sections_dir=sections.parent,
            output_dir=destination,
            output_name="blade",
            input_plan=plan,
            backend=backend,
            verbose=True,
        )
        result.append((case, data, job))
    return result


def build_catia(matrix: Path) -> None:
    """显式从已安装 wheel 生成 CATIA 候选及特征树证据，不写批准字段。"""
    if "site-packages" not in Path(autoblade.__file__).parts:
        raise RuntimeError("CATIA candidates require a non-editable installed wheel.")
    planned = jobs(matrix, BackendName.CATIA, matrix)
    for case, data, job in planned:
        print(f"Generating CATIA candidate: {data['case_id']}", flush=True)
        started = time.monotonic()
        get_backend(BackendName.CATIA).build(job)
        required = REQUIRED_FEATURES + (
            ("trailing_edge_lower_guide",) if not job.input_plan.is_sharp else ()
        )
        inspect_artifact(job.output_paths[0], required_features=required)
        text = job.output_paths[1].read_text(encoding="utf-8", errors="strict")
        if "AP242" not in text or "MANIFOLD_SOLID_BREP" not in text:
            raise ValueError("Expected a CATIA AP242 solid STEP.")
        record = {
            "status": "generated_candidate",
            "approval_status": PENDING,
            "input_manifest_sha256": sha256((case / "candidate.json").read_bytes()),
            "elapsed_seconds": time.monotonic() - started,
            "package_file": autoblade.__file__,
            "feature_tree": "passed",
            "artifacts_sha256": {
                p.name: sha256(p.read_bytes()) for p in job.output_paths
            },
        }
        (job.output_dir / "record.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )


def build_freecad(matrix: Path, output: Path) -> dict:
    """逐案例独立建模并记录身份；CATIA 暂不可用时仍可完成这一阶段。"""
    planned = jobs(matrix, BackendName.FREECAD, output)
    output.mkdir(parents=True, exist_ok=False)
    before = instances()
    records = []
    for case, data, job in planned:
        print(f"Measuring FreeCAD candidate: {data['case_id']}", flush=True)
        destination = output / data["case_id"]
        destination.mkdir()
        started = time.monotonic()
        with (
            (destination / "build.log").open("x", encoding="utf-8") as stream,
            redirect_stdout(stream),
        ):
            get_backend(BackendName.FREECAD).build(job)
        wait_instances(before)
        build_seconds = time.monotonic() - started
        runner = next(
            json.loads(line)
            for line in (destination / "build.log").read_text().splitlines()
            if line.startswith('{"schema_version": "autoblade.freecad/result/')
        )
        record = {
            "case_id": data["case_id"],
            "role": data["role"],
            "build_seconds": build_seconds,
            "peak_rss_kib": runner["peak_rss_kib"],
            "runner_status": runner["status"],
            "input_manifest_sha256": sha256((case / "candidate.json").read_bytes()),
            "request_sha256": runner["request_sha256"],
            "artifacts_sha256": {
                p.name: sha256(p.read_bytes()) for p in job.output_paths
            },
            "properties": runner["measurements"]["solid"],
        }
        records.append(record)
        (output / "progress.json").write_text(
            json.dumps(records, indent=2) + "\n", encoding="utf-8"
        )
    by_name = {record["case_id"]: record for record in records}
    affine = {
        name: affine_residual(
            by_name["single-sharp"]["properties"],
            by_name[name]["properties"],
            transform,
        )
        for name, transform in TRANSFORMS.items()
    }
    summary = {
        "schema": "autoblade.golden.candidate-build/v1",
        "approval_status": PENDING,
        "cases": records,
        "affine": affine,
        "instances_before": sorted(before),
        "instances_after": sorted(instances()),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return summary


def compare_candidates(matrix: Path, models: Path, output: Path) -> dict:
    """对已生成且摘要未变的双后端候选测量；不重建、覆盖或自动批准 CAD。"""
    built = json.loads((models / "summary.json").read_text())
    if built["schema"] != "autoblade.golden.candidate-build/v1":
        raise ValueError("Missing completed FreeCAD candidate build.")
    planned = []
    for record in built["cases"]:
        name = record["case_id"]
        case = fixture_path(matrix, name)
        data = load_candidate(case, require_catia=record["role"] != "performance")
        if (
            sha256((case / "candidate.json").read_bytes())
            != record["input_manifest_sha256"]
        ):
            raise ValueError("FreeCAD candidate input identity changed.")
        model = fixture_path(models, name + "/model")
        for filename, digest in record["artifacts_sha256"].items():
            if sha256(fixture_path(model, filename).read_bytes()) != digest:
                raise ValueError("FreeCAD candidate artifact fingerprint mismatch.")
        if data["role"] != "performance":
            planned.append((case, data, model, record))
    output.mkdir(parents=True, exist_ok=False)
    before = instances()
    reports, records = {}, []
    for case, data, model, record in planned:
        destination = output / data["case_id"]
        destination.mkdir()
        report = measure_artifacts(
            case=case,
            output=destination,
            native=model / "blade.FCStd",
            step=model / "blade.stp",
            digest=record["request_sha256"],
            timeout=900,
            candidate=True,
        )
        wait_instances(before)
        if report["status"] != "measured_candidate":
            raise RuntimeError(
                f"Candidate measurement failed: {destination / 'result.json'}"
            )
        reports[data["case_id"]] = report
        records.append(
            {
                **record,
                "cross_backend": report["cross_backend"],
            }
        )
        (output / "progress.json").write_text(
            json.dumps(records, indent=2) + "\n", encoding="utf-8"
        )
    affine = {
        name: {
            kind: affine_residual(
                reports["single-sharp"]["properties"][kind],
                reports[name]["properties"][kind],
                transform,
            )
            for kind in ("native", "catia")
        }
        for name, transform in TRANSFORMS.items()
    }
    summary = {
        "schema": "autoblade.golden.candidate-review/v1",
        "approval_status": PENDING,
        "comparison_policy": "measurements_only_user_judgment",
        "cases": records,
        "affine": affine,
        "instances_before": sorted(before),
        "instances_after": sorted(instances()),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("--output", required=True, type=Path)
    catia_command = commands.add_parser("catia")
    catia_command.add_argument("--matrix", required=True, type=Path)
    freecad_command = commands.add_parser("freecad")
    freecad_command.add_argument("--matrix", required=True, type=Path)
    freecad_command.add_argument("--output", required=True, type=Path)
    compare_command = commands.add_parser("compare")
    compare_command.add_argument("--matrix", required=True, type=Path)
    compare_command.add_argument("--models", required=True, type=Path)
    compare_command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.output.resolve())
    elif args.command == "catia":
        build_catia(args.matrix.resolve(strict=True))
    elif args.command == "freecad":
        build_freecad(args.matrix.resolve(strict=True), args.output.resolve())
    else:
        compare_candidates(
            args.matrix.resolve(strict=True),
            args.models.resolve(strict=True),
            args.output.resolve(),
        )


if __name__ == "__main__":
    main()
