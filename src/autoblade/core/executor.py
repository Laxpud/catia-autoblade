from collections.abc import Iterable
import sys

from .jobs import BladeBuildJob, BuildResult
from .backend import BackendError, BackendName


def execute_job(job: BladeBuildJob, *, blade_creator=None) -> BuildResult:
    """执行一个已规划任务；输入模式和文件组合不在本层重新推断。"""
    if blade_creator is None:
        from ..adapters.cad.factory import get_backend

        get_backend(job.backend).build(job)
        return BuildResult(job=job, status="success")
    if job.backend != BackendName.CATIA:
        raise ValueError("blade_creator injection is only supported for CATIA jobs.")

    blade_creator(
        job.airfoil_filename,
        job.blade_sections_filename,
        job.output_dir,
        job.output_name,
        airfoil_dir=job.airfoil_dir,
        blade_sections_dir=job.blade_sections_dir,
        keep_failed_part=job.keep_failed_part,
        input_plan=job.input_plan,
    )
    return BuildResult(job=job, status="success")


def execute_jobs(
    jobs: Iterable[BladeBuildJob],
    *,
    blade_creator=None,
) -> list[BuildResult]:
    """逐个执行任务并保留全部结果；单个失败不会阻断后续任务。"""
    planned = list(jobs)
    if len({job.backend for job in planned}) > 1:
        raise ValueError("A single execution cannot mix CAD backends.")
    results: list[BuildResult] = []
    for job in planned:
        try:
            results.append(execute_job(job, blade_creator=blade_creator))
        except Exception as error:
            if job.verbose and isinstance(error, BackendError) and error.diagnostics:
                print(error.diagnostics, file=sys.stderr)
            results.append(
                BuildResult(
                    job=job,
                    status="failed",
                    error=str(error),
                    error_code=error.code if isinstance(error, BackendError) else "build_failed",
                )
            )
    return results
