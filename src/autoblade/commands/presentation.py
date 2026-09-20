from collections.abc import Iterable

import typer

from ..core.jobs import BladeBuildJob
from ..core.sweep import SweepPlan


def show_job_preview(jobs: Iterable[BladeBuildJob]) -> list[BladeBuildJob]:
    """展示输入模式、任务总数、输出位置和已有文件覆盖风险。"""
    planned = list(jobs)
    typer.echo(f"[INFO] Planned build jobs: {len(planned)}")
    for index, job in enumerate(planned, start=1):
        airfoil = job.airfoil_filename or "per-section references"
        typer.echo(
            f"  {index}. backend={job.backend.value}, mode={job.mode}, airfoil={airfoil}, "
            f"section={job.blade_sections_filename}"
        )
        typer.echo(f"     output={job.output_dir / job.output_name}")
        for artifact in job.artifacts:
            typer.echo(f"     {artifact.kind}={artifact.path}")
        existing = [path for path in job.output_paths if path.exists()]
        if existing:
            names = ", ".join(path.name for path in existing)
            typer.echo(f"     overwrite={names}")
    return planned


def show_sweep_preview(plan: SweepPlan) -> None:
    """完整展示扫描选择、组合数量、任务、磁盘覆盖风险和稳定清单。"""
    airfoils = ", ".join(plan.airfoil_filenames)
    sections = ", ".join(plan.blade_sections_filenames)
    typer.echo(
        f"[INFO] Selected airfoils ({len(plan.airfoil_filenames)}): {airfoils}"
    )
    typer.echo(
        "[INFO] Selected six-column section templates "
        f"({len(plan.blade_sections_filenames)}): {sections}"
    )
    typer.echo(
        "[INFO] Combination: cartesian "
        f"({len(plan.airfoil_filenames)} x "
        f"{len(plan.blade_sections_filenames)} = {len(plan.jobs)})"
    )
    show_job_preview(plan.jobs)

    existing = [
        path
        for job in plan.jobs
        for path in job.output_paths
        if path.exists()
    ]
    typer.echo(f"[INFO] Existing output conflicts: {len(existing)}")
    for path in existing:
        typer.echo(f"  - {path}")
    typer.echo("[INFO] Stable sweep manifest:")
    typer.echo(plan.to_json())
