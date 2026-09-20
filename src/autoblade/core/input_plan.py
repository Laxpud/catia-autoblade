import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .input_validation import (
    InputValidationError,
    SectionParameters,
    read_airfoil_csv,
    read_section_parameter_table,
)


CANONICAL_AIRFOIL_FILENAME = re.compile(r"[a-z0-9][a-z0-9_-]*\.csv")
BladeMode = Literal["single", "multi"]
AirfoilPoint = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class AirfoilInput:
    """一个已经解析并通过校验的唯一翼型输入。"""

    filename: str
    path: Path
    points: tuple[AirfoilPoint, ...]
    is_sharp: bool
    # 原始 CSV 字节摘要随解析结果闭合；空值只兼容旧 CATIA 手工构造的计划。
    source_sha256: str = ""


@dataclass(frozen=True, slots=True)
class BladeInputPlan:
    """进入 CATIA 前已经闭合所有文件引用的叶片运行计划。"""

    mode: BladeMode
    blade_sections_path: Path
    sections: tuple[SectionParameters, ...]
    airfoils: tuple[AirfoilInput, ...]
    is_sharp: bool
    blade_sections_sha256: str = ""


def inspect_section_mode(blade_sections_path: str | Path) -> BladeMode:
    """只读取表头以供 CLI 规划交互和输出名称。"""
    path = Path(blade_sections_path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            header = next(reader, None)
    except (OSError, UnicodeError, csv.Error) as error:
        raise InputValidationError(
            path,
            f"cannot inspect blade section definition CSV: {error}",
        ) from error

    if header is None:
        raise InputValidationError(path, "CSV is empty; expected a header row")
    return "multi" if "airfoil" in header else "single"


def build_blade_input_plan(
    blade_sections_path: str | Path,
    airfoil_dir: str | Path,
    fallback_airfoil_filename: str | None,
    *,
    airfoil_reader: Callable[
        [str | Path],
        list[AirfoilPoint],
    ] = read_airfoil_csv,
) -> BladeInputPlan:
    """解析截面和唯一翼型，并保证所有错误都发生在 COM 初始化前。"""
    section_path = Path(blade_sections_path)
    section_digest = _source_sha256(section_path)
    table = read_section_parameter_table(section_path)
    _require_unchanged_source(section_path, section_digest)
    mode: BladeMode = "multi" if table.has_airfoil_column else "single"

    if mode == "multi" and fallback_airfoil_filename is not None:
        raise InputValidationError(
            section_path,
            "--airfoil cannot be combined with a section file that has an airfoil column",
            field="airfoil",
        )
    if mode == "single" and fallback_airfoil_filename is None:
        raise InputValidationError(
            section_path,
            "single-airfoil blade section definitions require an airfoil filename",
            field="airfoil",
        )

    # 1. 先为每个截面确定显式翼型，避免几何层再推断兼容模式。
    sections: list[SectionParameters] = []
    first_line_by_airfoil: dict[str, int] = {}
    for section, source_line in zip(
        table.sections,
        table.source_lines,
        strict=True,
    ):
        planned_section = dict(section)
        if mode == "multi":
            airfoil_filename = str(planned_section["airfoil_filename"])
        else:
            airfoil_filename = fallback_airfoil_filename
        planned_section["airfoil_filename"] = airfoil_filename
        sections.append(planned_section)
        first_line_by_airfoil.setdefault(airfoil_filename, source_line)

    # 2. 按首次使用顺序解析唯一文件；同一翼型不会被重复读取。
    airfoils: list[AirfoilInput] = []
    for airfoil_filename, source_line in first_line_by_airfoil.items():
        airfoil_path = resolve_airfoil_reference(
            airfoil_dir,
            airfoil_filename,
            source_path=section_path,
            source_line=source_line,
        )
        digest = _source_sha256(airfoil_path)
        points = tuple(airfoil_reader(airfoil_path))
        _require_unchanged_source(airfoil_path, digest)
        airfoils.append(
            AirfoilInput(
                filename=airfoil_filename,
                path=airfoil_path,
                points=points,
                is_sharp=points[0] == points[-1],
                source_sha256=digest,
            )
        )

    # 3. 尖、钝后缘需要不同数量的导引线，首版不允许在展向混用。
    expected_is_sharp = airfoils[0].is_sharp
    mismatched_airfoil = next(
        (
            airfoil
            for airfoil in airfoils[1:]
            if airfoil.is_sharp != expected_is_sharp
        ),
        None,
    )
    if mismatched_airfoil is not None:
        raise InputValidationError(
            section_path,
            "all airfoils in one blade must use the same trailing-edge topology; "
            f"{mismatched_airfoil.filename!r} differs from {airfoils[0].filename!r}",
            line=first_line_by_airfoil[mismatched_airfoil.filename],
            field="airfoil",
        )

    return BladeInputPlan(
        mode=mode,
        blade_sections_path=section_path.resolve(),
        sections=tuple(sections),
        airfoils=tuple(airfoils),
        is_sharp=expected_is_sharp,
        blade_sections_sha256=section_digest,
    )


def _source_sha256(path: Path) -> str:
    """规划时固定 CSV 来源摘要，执行和追溯不再依赖可变工作区文件。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise InputValidationError(path, f"cannot snapshot input source: {error}") from error


def _require_unchanged_source(path: Path, expected: str) -> None:
    """普通并发编辑若跨越解析窗口则拒绝计划，避免点数据与来源摘要不一致。"""
    if _source_sha256(path) != expected:
        raise InputValidationError(path, "input changed while it was being parsed; retry planning")


def resolve_airfoil_reference(
    airfoil_dir: str | Path,
    airfoil_filename: str,
    *,
    source_path: str | Path,
    source_line: int | None = None,
) -> Path:
    """把受限 basename 解析为翼型目录内的精确普通文件。"""
    source = Path(source_path)
    if not CANONICAL_AIRFOIL_FILENAME.fullmatch(airfoil_filename):
        raise InputValidationError(
            source,
            "airfoil must be a lowercase CSV basename using letters, numbers, '-' or '_'",
            line=source_line,
            field="airfoil",
        )

    directory = Path(airfoil_dir)
    try:
        resolved_directory = directory.resolve(strict=True)
        candidates = [
            candidate
            for candidate in directory.iterdir()
            if candidate.is_file() and candidate.suffix.lower() == ".csv"
        ]
    except OSError as error:
        raise InputValidationError(
            source,
            f"cannot inspect airfoil directory {directory.resolve()}: {error}",
            line=source_line,
            field="airfoil",
        ) from error

    # Windows 文件系统通常忽略大小写；显式拒绝别名可保证 CSV 引用可移植。
    names_by_casefold: dict[str, list[str]] = {}
    for candidate in candidates:
        names_by_casefold.setdefault(candidate.name.casefold(), []).append(
            candidate.name
        )
    ambiguous_names = [
        names for names in names_by_casefold.values() if len(names) > 1
    ]
    if ambiguous_names:
        names = ", ".join(sorted(ambiguous_names[0]))
        raise InputValidationError(
            source,
            f"airfoil directory contains case-insensitive filename aliases: {names}",
            line=source_line,
            field="airfoil",
        )

    candidate = next(
        (item for item in candidates if item.name == airfoil_filename),
        None,
    )
    if candidate is None:
        case_alias = names_by_casefold.get(airfoil_filename.casefold())
        if case_alias:
            constraint = (
                "airfoil filename must match exact spelling; found "
                f"{case_alias[0]!r}"
            )
        else:
            constraint = f"referenced airfoil file not found: {airfoil_filename}"
        raise InputValidationError(
            source,
            constraint,
            line=source_line,
            field="airfoil",
        )

    try:
        resolved_candidate = candidate.resolve(strict=True)
    except OSError as error:
        raise InputValidationError(
            source,
            f"cannot resolve referenced airfoil file {airfoil_filename}: {error}",
            line=source_line,
            field="airfoil",
        ) from error
    if not resolved_candidate.is_relative_to(resolved_directory):
        raise InputValidationError(
            source,
            "referenced airfoil file resolves outside the configured airfoil directory",
            line=source_line,
            field="airfoil",
        )
    return resolved_candidate
