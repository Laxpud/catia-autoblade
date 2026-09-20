from pathlib import Path

from collections.abc import Sequence

import typer

from ..config.manager import ConfigManager
from ..core.backend import BackendName
from .backend_options import resolve_backend_options
from ..core.executor import execute_jobs
from ..core.input_plan import inspect_section_mode
from ..core.jobs import BuildResult
from ..core.sweep import SweepPlan, SweepPlanner
from ..utils.file_scanner import get_available_files
from .presentation import show_sweep_preview


class SweepBuildError(Exception):
    """至少一个扫描任务失败；完整结构化结果仍保留给 Python 调用方。"""

    def __init__(self, results: list[BuildResult]) -> None:
        self.results = results
        failed = sum(result.status == "failed" for result in results)
        super().__init__(
            f"Sweep completed with {failed} failed task(s) out of {len(results)}."
        )


def run_sweep_command(
    airfoils: Sequence[str] | None,
    sections: Sequence[str] | None,
    output: str | None,
    dry_run: bool,
    interactive: bool,
    *,
    config_manager: ConfigManager | None = None,
    backend: BackendName | None = None,
    timeout_seconds: float | None = None,
    dependency_override: Path | None = None,
    verbose: bool = False,
    keep_failed_part: bool = False,
    sweep_processor=None,
) -> SweepPlan | list[BuildResult]:
    """规划显式笛卡尔积；dry-run 在共享 Executor 边界前直接返回。"""
    manager = config_manager or ConfigManager()
    config = manager.load_runtime()
    backend_options = resolve_backend_options(
        config, backend=backend, timeout_seconds=timeout_seconds,
        dependency_override=dependency_override, verbose=verbose,
        keep_failed_part=keep_failed_part,
    )
    airfoil_files, blade_sections_files = get_available_files(
        airfoil_dir=config.paths.airfoil_dir,
        blade_sections_dir=config.paths.blade_sections_dir,
    )
    if not airfoil_files:
        raise ValueError("No airfoil files were found.")
    if not blade_sections_files:
        raise ValueError("No blade section definition files were found.")

    selected_airfoils = list(airfoils or ())
    selected_sections = list(sections or ())
    if interactive:
        from ..interactive.prompts import (
            confirm_execution,
            confirm_output_dir,
            select_airfoils,
            select_sections,
        )

        eligible_sections = [
            name
            for name in blade_sections_files
            if inspect_section_mode(config.paths.blade_sections_dir / name)
            == "single"
        ]
        if not eligible_sections:
            raise ValueError("No six-column section templates were found.")
        if not selected_airfoils:
            selected_airfoils = select_airfoils(airfoil_files)
        if not selected_sections:
            selected_sections = select_sections(eligible_sections, multi=True)
        output_default = (
            manager.resolve_cli_path(output)
            if output
            else config.paths.output_dir
        )
        output_dir = manager.resolve_cli_path(
            confirm_output_dir(str(output_default))
        )
    else:
        if not selected_airfoils or not selected_sections:
            raise ValueError(
                "Non-interactive sweep requires at least one explicit "
                "--airfoil and --section."
            )
        output_dir = (
            manager.resolve_cli_path(output)
            if output
            else config.paths.output_dir
        )

    _validate_selected_files(
        selected_airfoils,
        available=airfoil_files,
        label="Airfoil",
    )
    _validate_selected_files(
        selected_sections,
        available=blade_sections_files,
        label="Blade section definition",
    )

    planner = SweepPlanner(
        output_dir,
        airfoil_dir=config.paths.airfoil_dir,
        blade_sections_dir=config.paths.blade_sections_dir,
        output_name_template=config.defaults.output_name_template,
        author=config.defaults.author,
        **backend_options,
    )
    plan = planner.plan(selected_airfoils, selected_sections)
    show_sweep_preview(plan)
    if dry_run:
        typer.echo("[INFO] Dry run complete; CAD was not started.")
        return plan
    if interactive:
        confirm_execution()

    processor = sweep_processor or execute_jobs
    results = processor(plan.jobs)
    if len(results) != len(plan.jobs):
        raise ValueError(
            "Sweep executor returned "
            f"{len(results)} result(s) for {len(plan.jobs)} job(s)."
        )
    success_count = sum(result.status == "success" for result in results)
    for result in results:
        if result.status == "failed":
            typer.echo(
                "[ERROR] Failed sweep combination for "
                f"airfoil={result.job.airfoil_filename}, "
                f"section={result.job.blade_sections_filename}: {result.error}",
                err=True,
            )
    typer.echo(
        f"[INFO] Sweep completed: {success_count}/{len(results)} successful."
    )
    if success_count != len(results):
        raise SweepBuildError(results)
    return results


def _validate_selected_files(
    selected: Sequence[str],
    *,
    available: Sequence[str],
    label: str,
) -> None:
    """要求每个扫描输入都来自配置目录中的显式 CSV basename。"""
    missing = sorted(set(selected) - set(available))
    if missing:
        raise ValueError(f"{label} file not found: {missing[0]!r}.")
