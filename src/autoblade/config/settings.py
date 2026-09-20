from pathlib import Path
from typing import Literal

from ..core.backend import BackendName

from pydantic import BaseModel, ConfigDict, Field


CURRENT_CONFIG_SCHEMA_VERSION = "4.0.0"


class StrictConfigModel(BaseModel):
    """拒绝未声明字段，避免旧程序在保存时静默丢失新版配置。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PathsConfig(StrictConfigModel):
    """配置文件中保存的路径契约。"""

    input_dir: Path = Path("input")
    output_dir: Path = Path("output")
    # 这两个目录的相对值以 input_dir 为基准，便于整体迁移输入树。
    airfoil_dir: Path = Path("airfoils")
    blade_sections_dir: Path = Path("blade_sections")


class DefaultsConfig(StrictConfigModel):
    """不由 CLI 显式指定时采用的运行默认值。"""

    backend: BackendName = BackendName.CATIA
    author: str = ""
    output_name_template: str = "{blade}"


class FreeCADConfig(StrictConfigModel):
    """认证入口固定为 Flatpak；超时单位为秒，不接受自由 shell 命令。"""

    launcher: Literal["flatpak"] = "flatpak"
    app_id: str = Field(default="org.freecad.FreeCAD", pattern=r"^[A-Za-z][A-Za-z0-9_.-]+$")
    timeout_seconds: float = Field(default=900, gt=0, allow_inf_nan=False)


class AppConfig(StrictConfigModel):
    """持久化配置及其运行时解析结果共用的模型。"""

    paths: PathsConfig = Field(default_factory=PathsConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    freecad: FreeCADConfig = Field(default_factory=FreeCADConfig)
    version: str = CURRENT_CONFIG_SCHEMA_VERSION
