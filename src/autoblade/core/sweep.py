from typing import Unpack
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .input_plan import inspect_section_mode
from .input_validation import InputValidationError
from .jobs import BladeBuildJob
from .backend import BackendOptions
from .planner import (
    _resolve_section_file,
    _validate_output_conflicts,
    plan_create_job,
)


SWEEP_MANIFEST_SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class SweepPlan:
    """一次显式笛卡尔积扫描的选择范围、稳定顺序和闭合任务。"""

    airfoil_filenames: tuple[str, ...]
    blade_sections_filenames: tuple[str, ...]
    jobs: tuple[BladeBuildJob, ...]

    def __post_init__(self) -> None:
        """清单只有一个 backend；空计划和混合后端均无法表达合法扫描。"""
        if not self.jobs or len({job.backend for job in self.jobs}) != 1:
            raise ValueError("Sweep requires non-empty jobs with one CAD backend.")

    def as_dict(self) -> dict[str, object]:
        """返回只含 JSON 基础类型的版本化任务清单。"""
        manifest_jobs: list[dict[str, object]] = []
        for index, job in enumerate(self.jobs, start=1):
            manifest_jobs.append(
                {
                    "job_id": f"sweep-{index:04d}",
                    "mode": job.mode,
                    "airfoil": job.airfoil_filename,
                    "blade_sections": job.blade_sections_filename,
                    "output_dir": str(job.output_dir),
                    "output_name": job.output_name,
                    "artifacts": [artifact.as_dict() for artifact in job.artifacts],
                }
            )

        return {
            "schema_version": SWEEP_MANIFEST_SCHEMA_VERSION,
            "planner": "sweep",
            "backend": self.jobs[0].backend.value,
            "combination": "cartesian",
            "selection": {
                "airfoils": list(self.airfoil_filenames),
                "blade_sections": list(self.blade_sections_filenames),
            },
            "job_count": len(self.jobs),
            "jobs": manifest_jobs,
        }

    def to_json(self) -> str:
        """按固定键排序序列化清单，便于 dry-run 和黄金文件逐字回归。"""
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


class SweepPlanner:
    """只组合显式选择的翼型与六列截面模板。

    首版扫描契约固定为 airfoil-major 的 Cartesian product：翼型 basename
    先按字典序排序，每个翼型内部再按截面 basename 排序。目录中未选择的
    文件不会参与规划，自包含七列文件也不能被外部翼型再次组合。
    """

    def __init__(
        self,
        output_base_dir: str | Path,
        *,
        airfoil_dir: str | Path,
        blade_sections_dir: str | Path,
        output_name_template: str,
        author: str,
        **backend_options: Unpack[BackendOptions],
    ) -> None:
        self.output_base_dir = Path(output_base_dir).resolve()
        self.airfoil_dir = Path(airfoil_dir).resolve()
        self.blade_sections_dir = Path(blade_sections_dir).resolve()
        self.output_name_template = output_name_template
        self.author = author
        self.backend_options = backend_options

    def plan(
        self,
        airfoil_filenames: Iterable[str],
        blade_sections_filenames: Iterable[str],
    ) -> SweepPlan:
        """校验显式选择并生成可直接交给共享 Executor 的闭合任务。"""
        airfoils = _stable_selection(airfoil_filenames, label="airfoil")
        sections = _stable_selection(
            blade_sections_filenames,
            label="blade section definition",
        )

        # 1. 在展开组合前一次性检查模板模式，保证七列自包含定义不会产生
        # 部分任务，也不会因输入目录变化而被静默纳入扫描。
        for section_filename in sections:
            section_path = _resolve_section_file(
                self.blade_sections_dir,
                section_filename,
            )
            if inspect_section_mode(section_path) != "single":
                raise InputValidationError(
                    section_path,
                    "sweep only accepts six-column section templates; "
                    "self-contained files cannot be combined with external airfoils",
                    field="airfoil",
                )

        # 2. 固定 airfoil-major 顺序；每个组合仍复用 create Planner 完成完整
        # CSV 解析、跨文件引用闭合和输出命名，Builder 不感知组合来源。
        jobs = tuple(
            plan_create_job(
                airfoil_filename,
                section_filename,
                self.output_base_dir / Path(airfoil_filename).stem,
                airfoil_dir=self.airfoil_dir,
                blade_sections_dir=self.blade_sections_dir,
                output_name_template=self.output_name_template,
                author=self.author,
                **self.backend_options,
            )
            for airfoil_filename in airfoils
            for section_filename in sections
        )
        _validate_output_conflicts(jobs, scope="Sweep")
        return SweepPlan(
            airfoil_filenames=airfoils,
            blade_sections_filenames=sections,
            jobs=jobs,
        )


def _stable_selection(values: Iterable[str], *, label: str) -> tuple[str, ...]:
    """去重并排序显式 basename，同时拒绝把单个字符串误作字符序列。"""
    if isinstance(values, str):
        values = [values]
    selected = tuple(sorted(dict.fromkeys(values)))
    if not selected:
        raise ValueError(f"Sweep requires at least one explicit {label} selection.")
    return selected
