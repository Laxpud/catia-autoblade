from typing import Unpack
from collections.abc import Iterable
from pathlib import Path

from ..utils.output_naming import build_output_name
from .input_plan import build_blade_input_plan, inspect_section_mode
from .input_validation import InputValidationError
from .jobs import BladeBuildJob
from .backend import BackendName, BackendOptions


def plan_create_job(
    airfoil_filename: str | None,
    blade_sections_filename: str,
    output_dir: str | Path,
    *,
    airfoil_dir: str | Path,
    blade_sections_dir: str | Path,
    output_name_template: str,
    author: str,
    keep_failed_part: bool = False,
    backend: BackendName = BackendName.CATIA,
    timeout_seconds: float = 900,
    freecad_app_id: str = "org.freecad.FreeCAD",
    dependency_override: Path | None = None,
    verbose: bool = False,
) -> BladeBuildJob:
    """把一个明确模型定义规划为可直接执行的闭合任务。"""
    airfoil_path = Path(airfoil_dir).resolve()
    section_dir_path = Path(blade_sections_dir).resolve()
    section_path = _resolve_section_file(
        section_dir_path,
        blade_sections_filename,
    )

    # 完整解析必须发生在 Planner 内；Executor 后续启动 CATIA 时不再发现输入
    # 文件缺失、逐行翼型引用错误或后缘拓扑冲突。
    input_plan = build_blade_input_plan(
        section_path,
        airfoil_path,
        airfoil_filename,
    )
    output_name = build_output_name(
        output_name_template,
        airfoil_filename,
        blade_sections_filename,
        author=author,
        is_multi_airfoil=input_plan.mode == "multi",
    )
    return BladeBuildJob(
        mode=input_plan.mode,
        airfoil_filename=airfoil_filename,
        blade_sections_filename=blade_sections_filename,
        airfoil_dir=airfoil_path,
        blade_sections_dir=section_dir_path,
        output_dir=Path(output_dir).resolve(),
        output_name=output_name,
        input_plan=input_plan,
        keep_failed_part=keep_failed_part,
        backend=BackendName(backend),
        timeout_seconds=timeout_seconds,
        freecad_app_id=freecad_app_id,
        dependency_override=dependency_override,
        verbose=verbose,
    )


def plan_batch_jobs(
    airfoil_filename: str | None,
    blade_sections_filenames: Iterable[str],
    output_base_dir: str | Path,
    *,
    airfoil_dir: str | Path,
    blade_sections_dir: str | Path,
    output_name_template: str,
    author: str,
    **backend_options: Unpack[BackendOptions],
) -> list[BladeBuildJob]:
    """为多个模型定义生成稳定排序的任务，不执行隐式笛卡尔积。

    六列截面模板统一绑定同一个显式翼型；含 ``airfoil`` 列的文件已经
    自包含，始终以 ``None`` 作为后备翼型。多翼型文件与六列模板可以在
    同一批次中出现，但外部翼型只作用于后者。
    """
    section_files = sorted(dict.fromkeys(blade_sections_filenames))
    if not section_files:
        raise ValueError("No blade section definition files were selected.")

    section_dir_path = Path(blade_sections_dir).resolve()
    jobs: list[BladeBuildJob] = []
    for section_filename in section_files:
        section_path = _resolve_section_file(
            section_dir_path,
            section_filename,
        )
        mode = inspect_section_mode(section_path)
        if mode == "single" and airfoil_filename is None:
            raise InputValidationError(
                section_path,
                "six-column blade section definitions in batch require --airfoil",
                field="airfoil",
            )

        job_airfoil = airfoil_filename if mode == "single" else None
        output_subdir = (
            Path(job_airfoil).stem
            if job_airfoil is not None
            else Path(section_filename).stem
        )
        jobs.append(
            plan_create_job(
                job_airfoil,
                section_filename,
                Path(output_base_dir) / output_subdir,
                airfoil_dir=airfoil_dir,
                blade_sections_dir=section_dir_path,
                output_name_template=output_name_template,
                author=author,
                **backend_options,
            )
        )

    _validate_output_conflicts(jobs, scope="Batch")
    return jobs


def _validate_output_conflicts(
    jobs: Iterable[BladeBuildJob],
    *,
    scope: str,
) -> None:
    """拒绝同一计划内部的重复目标；磁盘覆盖风险由命令预览负责展示。"""
    targets: dict[Path, BladeBuildJob] = {}
    for job in jobs:
        for target in job.output_paths:
            normalized = target.resolve()
            if normalized in targets:
                other = targets[normalized]
                raise ValueError(
                    f"{scope} output conflict between "
                    f"{other.blade_sections_filename!r} and "
                    f"{job.blade_sections_filename!r}: {normalized}"
                )
            targets[normalized] = job


def _resolve_section_file(
    blade_sections_dir: Path,
    blade_sections_filename: str,
) -> Path:
    """将 CLI 中的截面 basename 限制在配置目录内并检查精确文件名。"""
    if Path(blade_sections_filename).name != blade_sections_filename:
        raise InputValidationError(
            blade_sections_dir / blade_sections_filename,
            "blade section definitions must be a CSV basename",
        )
    section_path = blade_sections_dir / blade_sections_filename
    if section_path.suffix.lower() != ".csv" or not section_path.is_file():
        raise InputValidationError(
            section_path,
            f"blade section definition file not found: {blade_sections_filename}",
        )
    return section_path
