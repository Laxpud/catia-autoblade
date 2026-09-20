"""内部 CAD 边界的数据契约；此模块不加载 CAD 运行时或发现外部插件。"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .jobs import BladeBuildJob


class BackendName(StrEnum):
    """一次调用只能选择一个后端；所有平台的默认值都是 CATIA。"""

    CATIA = "catia"
    FREECAD = "freecad"


@dataclass(frozen=True, slots=True)
class Artifact:
    """一个制品的用途、格式与绝对目标路径。两个制品共同构成成功结果。"""

    kind: Literal["native_model", "step"]
    format: Literal["CATPart", "FCStd", "STEP"]
    path: Path

    def as_dict(self) -> dict[str, str]:
        """返回 manifest 使用的基础类型表示。"""
        return {"kind": self.kind, "format": self.format, "path": str(self.path)}


def plan_artifacts(
    backend: BackendName,
    output_dir: Path,
    output_name: str,
) -> tuple[Artifact, Artifact]:
    """在 CAD 启动前固定真实扩展名；不依据系统或安装情况自动回退。"""
    selected = BackendName(backend)
    native_format = "CATPart" if selected == BackendName.CATIA else "FCStd"
    return (
        Artifact(
            "native_model", native_format, output_dir / f"{output_name}.{native_format}"
        ),
        Artifact("step", "STEP", output_dir / f"{output_name}.stp"),
    )


class BackendErrorCode(StrEnum):
    """后端失败分类，不把厂商异常文本当作供调用方分支判断的协议。"""

    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    PROTOCOL = "protocol"
    GEOMETRY = "geometry"
    ARTIFACT_VALIDATION = "artifact_validation"
    CLEANUP = "cleanup"


class BackendOptions(TypedDict, total=False):
    """Planner 接收的内部选项，所有命令在同一调用内共享一次解析结果。"""

    backend: BackendName
    timeout_seconds: float
    freecad_app_id: str
    dependency_override: Path | None
    verbose: bool
    keep_failed_part: bool


class BackendError(RuntimeError):
    """保留机器可读失败类别以及仅在 verbose 下显示的子进程诊断。"""

    def __init__(
        self,
        backend: BackendName,
        code: BackendErrorCode | str,
        message: str,
        *,
        diagnostics: str = "",
    ) -> None:
        self.backend = BackendName(backend)
        self.code = BackendErrorCode(code)
        self.verbose = False
        self.diagnostics = diagnostics
        super().__init__(message)


class CadBackend(Protocol):
    """执行一个已闭合任务，失败抛异常，中断保持 KeyboardInterrupt 语义。"""

    def build(self, job: "BladeBuildJob") -> None:
        """成功必须拥有完整制品集；生命周期完全由具体 Adapter 管理。"""
        ...
