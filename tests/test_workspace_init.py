from pathlib import Path
import json

import pytest

from autoblade.commands import initialize
from autoblade.config.manager import ConfigManager
from autoblade.core.input_plan import build_blade_input_plan
from autoblade.interactive import prompts


def test_init_creates_external_workspace_with_optional_examples(
    tmp_path: Path,
) -> None:
    target = tmp_path / "blade-workspace"

    plan = initialize.run_init_command(
        target,
        with_examples=True,
        force=False,
        interactive=False,
    )

    assert plan.target == target.resolve()
    assert (target / "input" / "airfoils").is_dir()
    assert (target / "input" / "blade_sections").is_dir()
    assert (target / "output").is_dir()
    expected_airfoils = [
        "airfoil1_sharp.csv",
        "airfoil2_sharp.csv",
        "airfoil3_sharp.csv",
    ]
    assert sorted(
        path.name for path in (target / "input" / "airfoils").iterdir()
    ) == expected_airfoils
    section_path = (
        target
        / "input"
        / "blade_sections"
        / "example-blade-sections.csv"
    )
    assert section_path.is_file()
    input_plan = build_blade_input_plan(
        section_path,
        target / "input" / "airfoils",
        None,
    )
    assert input_plan.mode == "multi"
    assert len(input_plan.sections) == 89
    assert [airfoil.filename for airfoil in input_plan.airfoils] == (
        expected_airfoils
    )
    assert ConfigManager(target / "config.toml").load().version == "4.0.0"


def test_init_without_examples_only_creates_config_and_directories(
    tmp_path: Path,
) -> None:
    target = tmp_path / "blade-workspace"

    initialize.run_init_command(
        target,
        with_examples=False,
        force=False,
        interactive=False,
    )

    assert (target / "config.toml").is_file()
    assert list((target / "input" / "airfoils").iterdir()) == []
    assert list((target / "input" / "blade_sections").iterdir()) == []


def test_init_with_airfoil_library_copies_manifest_and_all_audited_airfoils(
    tmp_path: Path,
) -> None:
    target = tmp_path / "blade-workspace"

    initialize.run_init_command(
        target,
        with_examples=False,
        with_airfoil_library=True,
        force=False,
        interactive=False,
    )

    airfoil_dir = target / "input" / "airfoils"
    manifest = json.loads(
        (airfoil_dir / "manifest.json").read_text(encoding="utf-8")
    )
    expected_airfoils = [
        "airfoil1_sharp.csv",
        "airfoil2_sharp.csv",
        "airfoil3_sharp.csv",
    ]
    assert manifest["schema_version"] == 1
    assert [record["filename"] for record in manifest["airfoils"]] == (
        expected_airfoils
    )
    assert sorted(path.name for path in airfoil_dir.glob("*.csv")) == (
        expected_airfoils
    )
    assert list((target / "input" / "blade_sections").iterdir()) == []


def test_repeated_init_preserves_existing_managed_and_unrelated_files(
    tmp_path: Path,
) -> None:
    target = tmp_path / "blade-workspace"
    initialize.run_init_command(
        target,
        with_examples=True,
        with_airfoil_library=True,
        force=False,
        interactive=False,
    )
    config_file = target / "config.toml"
    config_file.write_text("user-owned config", encoding="utf-8")
    unrelated = target / "customer-input.csv"
    unrelated.write_text("private", encoding="utf-8")

    with pytest.raises(FileExistsError, match="--force"):
        initialize.run_init_command(
            target,
            with_examples=True,
            with_airfoil_library=True,
            force=False,
            interactive=False,
        )

    assert config_file.read_text(encoding="utf-8") == "user-owned config"
    assert unrelated.read_text(encoding="utf-8") == "private"

    initialize.run_init_command(
        target,
        with_examples=True,
        with_airfoil_library=True,
        force=True,
        interactive=False,
    )
    assert "version = \"4.0.0\"" in config_file.read_text(encoding="utf-8")
    assert (target / "input" / "airfoils" / "manifest.json").is_file()
    assert unrelated.read_text(encoding="utf-8") == "private"


def test_interactive_init_can_authorize_only_listed_conflicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "blade-workspace"
    initialize.run_init_command(
        target,
        with_examples=False,
        force=False,
        interactive=False,
    )
    confirmed = []
    monkeypatch.setattr(
        prompts,
        "confirm_workspace_overwrite",
        lambda paths: confirmed.extend(paths) or True,
    )

    initialize.run_init_command(
        target,
        with_examples=False,
        force=False,
        interactive=True,
    )

    assert confirmed == [target / "config.toml"]


def test_init_reports_unwritable_target_before_creating_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "read-only" / "workspace"

    def fail_probe(path: Path) -> None:
        raise PermissionError(f"read-only: {path}")

    monkeypatch.setattr(initialize, "_probe_target_write_access", fail_probe)

    with pytest.raises(PermissionError, match="read-only"):
        initialize.run_init_command(
            target,
            with_examples=False,
            force=False,
            interactive=False,
        )

    assert not target.exists()


def test_init_rejects_site_packages_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "site-packages"
    package_root.mkdir()
    monkeypatch.setattr(initialize.site, "getsitepackages", lambda: [package_root])
    monkeypatch.setattr(initialize.site, "getusersitepackages", lambda: "")

    with pytest.raises(ValueError, match="outside site-packages"):
        initialize.plan_workspace_initialization(
            package_root / "workspace",
            with_examples=False,
        )
