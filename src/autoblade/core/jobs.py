from dataclasses import dataclass
from pathlib import Path
import math
from typing import Literal

from .input_plan import BladeInputPlan, BladeMode
from .backend import Artifact, BackendName, plan_artifacts


BuildStatus = Literal["success", "failed"]


@dataclass(frozen=True, slots=True)
class BladeBuildJob:
    """一次输入引用、输出位置和建模选项均已确定的叶片任务。

    ``input_plan`` 在 Planner 阶段完成 CSV 解析和跨文件引用闭合，因此执行器
    不需要根据目录内容推断翼型，也不会把 Typer 参数带入 CATIA 建模流程。
    """

    mode: BladeMode
    airfoil_filename: str | None
    blade_sections_filename: str
    airfoil_dir: Path
    blade_sections_dir: Path
    output_dir: Path
    output_name: str
    input_plan: BladeInputPlan
    keep_failed_part: bool = False
    backend: BackendName = BackendName.CATIA
    timeout_seconds: float = 900
    freecad_app_id: str = "org.freecad.FreeCAD"
    dependency_override: Path | None = None
    verbose: bool = False

    def __post_init__(self) -> None:
        """拒绝未知后端和无限等待；直接 Python 调用与 CLI 具有相同边界。"""
        object.__setattr__(self, "backend", BackendName(self.backend))
        if (isinstance(self.timeout_seconds, bool) or not math.isfinite(self.timeout_seconds)
                or self.timeout_seconds <= 0):
            raise ValueError("timeout_seconds must be a finite positive number.")

    @property
    def artifacts(self) -> tuple[Artifact, Artifact]:
        """返回 backend-specific 逻辑制品集，规划和执行共享同一来源。"""
        return plan_artifacts(self.backend, self.output_dir, self.output_name)

    @property
    def output_paths(self) -> tuple[Path, Path]:
        """返回任务会覆盖或创建的原生模型与 STEP 路径。"""
        return tuple(artifact.path for artifact in self.artifacts)


@dataclass(frozen=True, slots=True)
class BuildResult:
    """记录一个任务的稳定执行结果，供 CLI 汇总而不丢失失败上下文。"""

    job: BladeBuildJob
    status: BuildStatus
    error: str | None = None
    error_code: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """提供旧批处理调用方使用的字典视图。"""
        result: dict[str, str | None] = {
            "status": self.status,
            "mode": self.job.mode,
            "airfoil": self.job.airfoil_filename,
            "section": self.job.blade_sections_filename,
        }
        if self.status == "success":
            result["output"] = str(self.job.output_dir)
        else:
            result["error"] = self.error
        return result
