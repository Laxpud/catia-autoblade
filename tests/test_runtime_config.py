from pathlib import Path

import pytest

from autoblade.commands.batch import BatchBuildError, run_batch_command
from autoblade.commands.create import run_create_command
from autoblade.config.manager import ConfigManager
from autoblade.core.jobs import BuildResult
from autoblade.core.input_validation import InputValidationError
from autoblade.interactive.prompts import PromptCancelled
from autoblade.utils.file_scanner import get_available_files
from autoblade.utils.output_naming import build_output_name


VALID_SECTIONS = """idx,scale/m,translate_x/m,translate_y/m,translate_z/m,rotate/deg
1,0.1,0,0,0,10
2,0.08,1,0,0,5
"""

MULTI_SECTIONS = """idx,scale/m,translate_x/m,translate_y/m,translate_z/m,rotate/deg,airfoil
1,0.1,0,0,0,10,foil.csv
2,0.08,1,0,0,5,foil.csv
"""

SHARP_AIRFOIL = """x,y,z
0,1,0
0,0.5,0.1
0,0,0
0,0.5,-0.1
0,1,0
"""


def _write_config(
    config_dir: Path,
    *,
    output_name_template: str = "{author}_{airfoil}_{idx}",
) -> ConfigManager:
    """创建一份路径与命名均偏离默认值的最小测试配置。"""
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    config_file.write_text(
        f"""version = "4.0.0"

[paths]
input_dir = "data"
output_dir = "artifacts"
airfoil_dir = "profiles"
blade_sections_dir = "sections"

[defaults]
author = "Ada"
output_name_template = "{output_name_template}"
""",
        encoding="utf-8",
    )
    return ConfigManager(config_file)


def _create_input_files(config_dir: Path) -> None:
    profiles = config_dir / "data" / "profiles"
    sections = config_dir / "data" / "sections"
    profiles.mkdir(parents=True)
    sections.mkdir(parents=True)
    (profiles / "foil.csv").write_text(SHARP_AIRFOIL, encoding="utf-8")
    (profiles / "ignored.txt").touch()
    (sections / "blade_sections-7.csv").write_text(
        VALID_SECTIONS,
        encoding="utf-8",
    )


def test_runtime_paths_are_resolved_from_config_location(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)

    runtime = manager.load_runtime()

    assert runtime.paths.input_dir == (config_dir / "data").resolve()
    assert runtime.paths.output_dir == (config_dir / "artifacts").resolve()
    assert runtime.paths.airfoil_dir == (config_dir / "data" / "profiles").resolve()
    assert runtime.paths.blade_sections_dir == (
        config_dir / "data" / "sections"
    ).resolve()


def test_cli_path_is_resolved_from_process_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_dir = tmp_path / "caller"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)

    assert ConfigManager.resolve_cli_path("custom-output") == (
        working_dir / "custom-output"
    ).resolve()


def test_scanner_uses_configured_input_directories(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)
    _create_input_files(config_dir)

    airfoils, sections = get_available_files(config_manager=manager)

    assert airfoils == ["foil.csv"]
    assert sections == ["blade_sections-7.csv"]


def test_output_name_uses_configured_template_fields() -> None:
    assert build_output_name(
        "{author}_{airfoil}_{idx}_{section}",
        "foil.csv",
        "blade_sections-7.csv",
        author="Ada",
    ) == "Ada_foil_7_blade_sections-7"


def test_blade_output_field_preserves_legacy_and_names_multi_airfoil() -> None:
    assert build_output_name(
        "{blade}",
        "foil.csv",
        "blade_sections-7.csv",
    ) == "foil_blade-7"
    assert build_output_name(
        "{blade}",
        None,
        "blade_sections-multi-airfoil.csv",
        is_multi_airfoil=True,
    ) == "blade-multi-airfoil"


def test_output_name_rejects_unknown_template_field() -> None:
    with pytest.raises(ValueError, match="Unsupported output name field"):
        build_output_name("{unknown}", "foil.csv", "blade_sections-7.csv")


def test_multi_output_name_rejects_single_airfoil_field() -> None:
    with pytest.raises(ValueError, match="unavailable for a multi-airfoil"):
        build_output_name(
            "{airfoil}_{idx}",
            None,
            "blade_sections-multi-airfoil.csv",
            is_multi_airfoil=True,
        )


def test_create_command_cli_output_overrides_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)
    _create_input_files(config_dir)
    working_dir = tmp_path / "caller"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    calls = []

    def fake_create(*args, **kwargs):
        calls.append((args, kwargs))

    run_create_command(
        "foil.csv",
        "blade_sections-7.csv",
        "cli-output",
        False,
        True,
        config_manager=manager,
        blade_creator=fake_create,
    )

    args, kwargs = calls[0]
    assert args == (
        "foil.csv",
        "blade_sections-7.csv",
        (working_dir / "cli-output").resolve(),
        "Ada_foil_7",
    )
    assert kwargs["airfoil_dir"] == (config_dir / "data" / "profiles").resolve()
    assert kwargs["blade_sections_dir"] == (
        config_dir / "data" / "sections"
    ).resolve()
    assert kwargs["keep_failed_part"] is True
    assert kwargs["input_plan"].mode == "single"


def test_create_command_uses_per_section_airfoils_without_fallback(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir, output_name_template="{blade}")
    _create_input_files(config_dir)
    section_path = (
        config_dir
        / "data"
        / "sections"
        / "blade_sections-multi-airfoil.csv"
    )
    section_path.write_text(MULTI_SECTIONS, encoding="utf-8")
    calls = []

    run_create_command(
        None,
        section_path.name,
        None,
        False,
        config_manager=manager,
        blade_creator=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    args, kwargs = calls[0]
    assert args == (
        None,
        "blade_sections-multi-airfoil.csv",
        (config_dir / "artifacts").resolve(),
        "blade-multi-airfoil",
    )
    assert kwargs["input_plan"].mode == "multi"


def test_create_command_rejects_fallback_for_multi_airfoil_file(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir, output_name_template="{blade}")
    _create_input_files(config_dir)
    section_path = (
        config_dir
        / "data"
        / "sections"
        / "blade_sections-multi-airfoil.csv"
    )
    section_path.write_text(MULTI_SECTIONS, encoding="utf-8")
    calls = []

    with pytest.raises(ValueError, match="cannot be used"):
        run_create_command(
            "foil.csv",
            section_path.name,
            None,
            False,
            config_manager=manager,
            blade_creator=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


def test_create_command_requires_airfoil_for_six_column_file(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)
    _create_input_files(config_dir)
    calls = []

    with pytest.raises(InputValidationError, match="require an airfoil"):
        run_create_command(
            None,
            "blade_sections-7.csv",
            None,
            False,
            config_manager=manager,
            blade_creator=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


def test_create_command_rejects_missing_explicit_airfoil(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)
    _create_input_files(config_dir)

    with pytest.raises(ValueError, match="Airfoil file not found"):
        run_create_command(
            "missing.csv",
            "blade_sections-7.csv",
            None,
            False,
            config_manager=manager,
        )


def test_interactive_create_cancels_before_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autoblade.interactive import prompts

    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)
    _create_input_files(config_dir)
    calls = []
    monkeypatch.setattr(
        prompts,
        "confirm_output_dir",
        lambda default: config_dir / "artifacts",
    )
    monkeypatch.setattr(
        prompts,
        "confirm_execution",
        lambda: (_ for _ in ()).throw(
            PromptCancelled("Build was cancelled before CATIA started.")
        ),
    )

    with pytest.raises(PromptCancelled, match="before CATIA started"):
        run_create_command(
            "foil.csv",
            "blade_sections-7.csv",
            None,
            True,
            config_manager=manager,
            blade_creator=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


def test_batch_command_uses_configured_output_and_template(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)
    _create_input_files(config_dir)
    calls = []

    def fake_batch(jobs):
        calls.extend(jobs)
        return [BuildResult(job=job, status="success") for job in jobs]

    run_batch_command(
        "foil.csv",
        "blade_sections-7.csv",
        None,
        False,
        False,
        config_manager=manager,
        batch_processor=fake_batch,
    )

    job = calls[0]
    assert job.airfoil_filename == "foil.csv"
    assert job.blade_sections_filename == "blade_sections-7.csv"
    assert job.output_dir == (config_dir / "artifacts" / "foil").resolve()
    assert job.output_name == "Ada_foil_7"
    assert job.input_plan.mode == "single"


def test_batch_command_raises_after_reporting_partial_failure(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "project"
    manager = _write_config(config_dir)
    _create_input_files(config_dir)
    section_dir = config_dir / "data" / "sections"
    (section_dir / "blade_sections-8.csv").write_text(
        VALID_SECTIONS,
        encoding="utf-8",
    )

    def fake_batch(jobs):
        return [
            BuildResult(job=jobs[0], status="failed", error="model failed"),
            BuildResult(job=jobs[1], status="success"),
        ]

    with pytest.raises(BatchBuildError) as raised:
        run_batch_command(
            "foil.csv",
            None,
            None,
            False,
            False,
            config_manager=manager,
            batch_processor=fake_batch,
        )

    assert [
        result.status for result in raised.value.results
    ] == ["failed", "success"]


def test_batch_core_applies_template_to_each_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autoblade.core import batch as batch_module

    calls = []

    def fake_create(*args, **kwargs):
        calls.append((args, kwargs))

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    (section_dir / "blade_sections-7.csv").write_text(
        VALID_SECTIONS,
        encoding="utf-8",
    )
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "foil.csv").write_text(SHARP_AIRFOIL, encoding="utf-8")
    monkeypatch.setattr(batch_module, "create_single_blade", fake_create)
    batch_module.batch_create_blades(
        ["foil.csv"],
        ["blade_sections-7.csv"],
        tmp_path / "artifacts",
        airfoil_dir=profile_dir,
        blade_sections_dir=section_dir,
        output_name_template="{author}_{airfoil}_{idx}",
        author="Ada",
    )

    args, kwargs = calls[0]
    assert args[3] == "Ada_foil_7"
    assert kwargs["airfoil_dir"] == profile_dir.resolve()
    assert kwargs["blade_sections_dir"] == section_dir.resolve()
    assert kwargs["keep_failed_part"] is False
    assert kwargs["input_plan"].mode == "single"


def test_batch_core_creates_multi_airfoil_section_file_only_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autoblade.core import batch as batch_module

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    (section_dir / "blade_sections-multi-airfoil.csv").write_text(
        MULTI_SECTIONS,
        encoding="utf-8",
    )
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "foil.csv").write_text(SHARP_AIRFOIL, encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        batch_module,
        "create_single_blade",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    results = batch_module.batch_create_blades(
        ["foil.csv", "other.csv"],
        ["blade_sections-multi-airfoil.csv"],
        tmp_path / "artifacts",
        airfoil_dir=profile_dir,
        blade_sections_dir=section_dir,
        output_name_template="{blade}",
        author="",
    )

    assert len(calls) == 1
    args, _ = calls[0]
    assert args[:4] == (
        None,
        "blade_sections-multi-airfoil.csv",
        tmp_path / "artifacts" / "blade_sections-multi-airfoil",
        "blade-multi-airfoil",
    )
    assert results[0]["mode"] == "multi"


def test_batch_core_rejects_multiple_airfoils_for_six_column_templates(
    tmp_path: Path,
) -> None:
    from autoblade.core import batch as batch_module

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    (section_dir / "blade_sections-7.csv").write_text(
        VALID_SECTIONS,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="belong to sweep"):
        batch_module.batch_create_blades(
            ["foil.csv", "other.csv"],
            ["blade_sections-7.csv"],
            tmp_path / "artifacts",
            airfoil_dir=tmp_path / "profiles",
            blade_sections_dir=section_dir,
            output_name_template="{blade}",
            author="",
        )
