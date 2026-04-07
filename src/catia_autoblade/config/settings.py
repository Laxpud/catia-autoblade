from pathlib import Path
from pydantic import BaseModel, Field


class PathsConfig(BaseModel):
    input_dir: Path = Field(default=Path("input"), validate_default=True)
    output_dir: Path = Field(default=Path("output"), validate_default=True)
    airfoil_dir: Path = Field(default=Path("input/airfoils"))
    section_params_dir: Path = Field(default=Path("input/section_params"))


class DefaultsConfig(BaseModel):
    author: str = ""
    output_name_template: str = "{airfoil}_blade-{idx}"


class AppConfig(BaseModel):
    paths: PathsConfig = Field(default_factory=PathsConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    version: str = "1.0.0"