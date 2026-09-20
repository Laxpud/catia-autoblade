import os
from pathlib import Path
import warnings

import pytest

from autoblade.config.manager import (
    ConfigCompatibilityError,
    ConfigManager,
    ConfigMigrationRequiredError,
    ConfigMigrationWarning,
)


CURRENT_CONFIG = """version = "4.0.0"

[paths]
input_dir = "input"
output_dir = "output"
airfoil_dir = "airfoils"
blade_sections_dir = "blade_sections"

[defaults]
author = "Ada"
output_name_template = "{blade}"
"""

PREVIOUS_CONFIG = """version = "2.0.0"

[paths]
input_dir = "input"
output_dir = "output"
airfoil_dir = "airfoils"
section_params_dir = "section_params"

[defaults]
author = "Ada"
output_name_template = "{blade}"
"""

LEGACY_CONFIG = r'''version = "1.0.0"

[paths]
input_dir = "input"
output_dir = "output"
airfoil_dir = 'input\airfoils'
section_params_dir = 'input\section_params'

[defaults]
author = "Ada"
output_name_template = "{airfoil}_blade-{idx}"
'''


def _write(path: Path, content: str = CURRENT_CONFIG) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_config_discovery_priority_is_explicit_workspace_user_defaults(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / "workspace"
    workspace = _write(working_dir / "config.toml")
    user = _write(tmp_path / "user" / "config.toml")
    explicit = _write(tmp_path / "explicit.toml")

    manager = ConfigManager.discover(
        explicit,
        working_dir=working_dir,
        user_config_file=user,
    )
    assert manager.source.kind == "explicit"
    assert manager.config_file == explicit.resolve()

    manager = ConfigManager.discover(
        working_dir=working_dir,
        user_config_file=user,
    )
    assert manager.source.kind == "workspace"
    assert manager.config_file == workspace.resolve()

    workspace.unlink()
    manager = ConfigManager.discover(
        working_dir=working_dir,
        user_config_file=user,
    )
    assert manager.source.kind == "user"
    assert manager.config_file == user.resolve()

    user.unlink()
    manager = ConfigManager.discover(
        working_dir=working_dir,
        user_config_file=user,
    )
    assert manager.source.kind == "defaults"
    assert manager.config_file == (working_dir / "config.toml").resolve()
    assert manager.load().version == "4.0.0"


def test_default_user_config_uses_canonical_autoblade_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert ConfigManager.default_user_config_file() == (
        tmp_path / "autoblade" / "config.toml"
    )
    assert ConfigManager.default_legacy_user_config_file() == (
        tmp_path / "catia-autoblade" / "config.toml"
    )


def test_legacy_user_directory_is_warning_fallback_when_new_path_is_absent(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / "workspace"
    canonical = tmp_path / "autoblade" / "config.toml"
    legacy = _write(tmp_path / "catia-autoblade" / "config.toml")

    with pytest.warns(ConfigMigrationWarning, match="legacy user configuration"):
        manager = ConfigManager.discover(
            working_dir=working_dir,
            user_config_file=canonical,
            legacy_user_config_file=legacy,
        )

    assert manager.source.kind == "legacy-user"
    assert manager.config_file == legacy.resolve()
    assert manager.load().defaults.author == "Ada"


def test_canonical_user_directory_wins_when_both_paths_exist(tmp_path: Path) -> None:
    working_dir = tmp_path / "workspace"
    canonical = _write(
        tmp_path / "autoblade" / "config.toml",
        CURRENT_CONFIG.replace('author = "Ada"', 'author = "Canonical"'),
    )
    legacy = _write(
        tmp_path / "catia-autoblade" / "config.toml",
        CURRENT_CONFIG.replace('author = "Ada"', 'author = "Legacy"'),
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager = ConfigManager.discover(
            working_dir=working_dir,
            user_config_file=canonical,
            legacy_user_config_file=legacy,
        )

    assert manager.source.kind == "user"
    assert manager.config_file == canonical.resolve()
    assert manager.load().defaults.author == "Canonical"
    assert not any(
        issubclass(item.category, ConfigMigrationWarning) for item in caught
    )


def test_legacy_user_location_migration_previews_backs_up_and_preserves_paths(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / "workspace"
    canonical = tmp_path / "autoblade" / "config.toml"
    legacy = _write(tmp_path / "catia-autoblade" / "config.toml")
    original = legacy.read_bytes()

    with pytest.warns(ConfigMigrationWarning):
        manager = ConfigManager.discover(
            working_dir=working_dir,
            user_config_file=canonical,
            legacy_user_config_file=legacy,
        )
    runtime_before = manager.load_runtime()
    plan = manager.plan_migration()

    assert plan is not None
    assert plan.config_file == legacy.resolve()
    assert plan.target_config_file == canonical.resolve()
    assert [change.field for change in plan.changes] == [
        "paths.input_dir",
        "paths.output_dir",
        "config_file",
    ]
    assert legacy.read_bytes() == original
    assert not canonical.exists()

    backup = manager.apply_migration(plan)

    assert backup.read_bytes() == original
    assert not legacy.exists()
    assert canonical.is_file()
    assert manager.config_file == canonical.resolve()
    assert manager.source.kind == "user"
    runtime_after = manager.load_runtime()
    assert runtime_after.paths.input_dir == runtime_before.paths.input_dir
    assert runtime_after.paths.output_dir == runtime_before.paths.output_dir
    assert manager.plan_migration() is None


def test_legacy_user_location_cannot_be_written_before_explicit_migration(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "autoblade" / "config.toml"
    legacy = _write(tmp_path / "catia-autoblade" / "config.toml")
    with pytest.warns(ConfigMigrationWarning):
        manager = ConfigManager.discover(
            working_dir=tmp_path / "workspace",
            user_config_file=canonical,
            legacy_user_config_file=legacy,
        )

    with pytest.raises(ConfigMigrationRequiredError, match="location migration"):
        manager.save(manager.load())


def test_location_migration_refuses_canonical_file_created_after_preview(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "autoblade" / "config.toml"
    legacy = _write(tmp_path / "catia-autoblade" / "config.toml")
    with pytest.warns(ConfigMigrationWarning):
        manager = ConfigManager.discover(
            working_dir=tmp_path / "workspace",
            user_config_file=canonical,
            legacy_user_config_file=legacy,
        )
    plan = manager.plan_migration()
    assert plan is not None
    _write(canonical, CURRENT_CONFIG.replace('author = "Ada"', 'author = "New"'))

    with pytest.raises(ConfigCompatibilityError, match="Refusing to overwrite"):
        manager.apply_migration(plan)

    assert legacy.is_file()
    assert 'author = "New"' in canonical.read_text(encoding="utf-8")


def test_legacy_schema_and_user_location_migrate_in_one_guarded_apply(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "autoblade" / "config.toml"
    legacy = _write(
        tmp_path / "catia-autoblade" / "config.toml",
        LEGACY_CONFIG,
    )
    with pytest.warns(ConfigMigrationWarning):
        manager = ConfigManager.discover(
            working_dir=tmp_path / "workspace",
            user_config_file=canonical,
            legacy_user_config_file=legacy,
        )
    with pytest.warns(ConfigMigrationWarning):
        runtime_before = manager.load_runtime()

    plan = manager.plan_migration()
    assert plan is not None
    assert plan.source_version == "1.0.0"
    assert plan.target_version == "4.0.0"
    assert plan.changes[-1].field == "config_file"

    backup = manager.apply_migration(plan)

    assert backup.read_text(encoding="utf-8") == LEGACY_CONFIG
    assert 'version = "4.0.0"' in canonical.read_text(encoding="utf-8")
    assert manager.load_runtime().paths.input_dir == runtime_before.paths.input_dir
    assert manager.plan_migration() is None


def test_explicit_relative_config_is_anchored_to_invocation_directory(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / "caller"
    config_file = _write(working_dir / "configs" / "blade.toml")

    manager = ConfigManager.discover(
        Path("configs") / "blade.toml",
        working_dir=working_dir,
    )

    assert manager.config_file == config_file.resolve()


def test_legacy_config_is_read_without_writing_and_paths_stay_stable(
    tmp_path: Path,
) -> None:
    config_file = _write(tmp_path / "config.toml", LEGACY_CONFIG)
    original = config_file.read_bytes()
    manager = ConfigManager(config_file)

    with pytest.warns(ConfigMigrationWarning):
        runtime = manager.load_runtime()

    assert runtime.paths.airfoil_dir == (tmp_path / "input" / "airfoils").resolve()
    assert runtime.paths.blade_sections_dir == (
        tmp_path / "input" / "blade_sections"
    ).resolve()
    assert runtime.defaults.output_name_template == "{airfoil}_blade-{idx}"
    assert config_file.read_bytes() == original


def test_legacy_config_migration_previews_backs_up_and_preserves_values(
    tmp_path: Path,
) -> None:
    config_file = _write(tmp_path / "config.toml", LEGACY_CONFIG)
    manager = ConfigManager(config_file)
    plan = manager.plan_migration()

    assert plan is not None
    assert plan.source_version == "1.0.0"
    assert [change.field for change in plan.changes] == [
        "version",
        "paths.section_params_dir",
        "paths.airfoil_dir",
        "defaults.backend",
        "freecad.launcher",
        "freecad.app_id",
        "freecad.timeout_seconds",
    ]

    backup = manager.apply_migration(plan)

    assert backup.read_text(encoding="utf-8") == LEGACY_CONFIG
    migrated_text = config_file.read_text(encoding="utf-8")
    assert 'version = "4.0.0"' in migrated_text
    assert 'airfoil_dir = "airfoils"' in migrated_text
    assert 'blade_sections_dir = "blade_sections"' in migrated_text
    assert "section_params_dir" not in migrated_text
    assert 'output_name_template = "{airfoil}_blade-{idx}"' in migrated_text
    assert manager.plan_migration() is None


def test_schema_2_config_migrates_field_and_default_directory(
    tmp_path: Path,
) -> None:
    config_file = _write(tmp_path / "config.toml", PREVIOUS_CONFIG)
    manager = ConfigManager(config_file)
    plan = manager.plan_migration()

    assert plan is not None
    assert plan.source_version == "2.0.0"
    assert [change.field for change in plan.changes] == [
        "version",
        "paths.section_params_dir",
        "defaults.backend",
        "freecad.launcher",
        "freecad.app_id",
        "freecad.timeout_seconds",
    ]

    manager.apply_migration(plan)
    migrated_text = config_file.read_text(encoding="utf-8")
    assert 'version = "4.0.0"' in migrated_text
    assert 'blade_sections_dir = "blade_sections"' in migrated_text
    assert "section_params_dir" not in migrated_text


def test_legacy_config_cannot_be_silently_saved(tmp_path: Path) -> None:
    config_file = _write(tmp_path / "config.toml", LEGACY_CONFIG)
    manager = ConfigManager(config_file)
    with pytest.warns(ConfigMigrationWarning):
        config = manager.load()

    with pytest.raises(ConfigMigrationRequiredError, match="config migrate"):
        manager.save(config)


def test_migration_rejects_file_changed_after_preview(tmp_path: Path) -> None:
    config_file = _write(tmp_path / "config.toml", LEGACY_CONFIG)
    manager = ConfigManager(config_file)
    plan = manager.plan_migration()
    assert plan is not None
    config_file.write_text(LEGACY_CONFIG + "\n# changed\n", encoding="utf-8")

    with pytest.raises(ConfigCompatibilityError, match="changed after"):
        manager.apply_migration(plan)


def test_future_and_unknown_schema_content_fail_safely(tmp_path: Path) -> None:
    future = _write(
        tmp_path / "future.toml",
        CURRENT_CONFIG.replace('version = "4.0.0"', 'version = "5.0.0"'),
    )
    with pytest.raises(ConfigCompatibilityError, match="newer than supported"):
        ConfigManager(future).load()

    unknown = _write(
        tmp_path / "unknown.toml",
        CURRENT_CONFIG + "\ncustomer_secret = \"keep-me\"\n",
    )
    original = unknown.read_bytes()
    with pytest.raises(ConfigCompatibilityError, match="Unknown configuration"):
        ConfigManager(unknown).load()
    assert unknown.read_bytes() == original


def test_current_schema_reports_removed_section_params_field(
    tmp_path: Path,
) -> None:
    old_field = CURRENT_CONFIG.replace(
        'blade_sections_dir = "blade_sections"',
        'section_params_dir = "section_params"',
    )
    config_file = _write(tmp_path / "removed-field.toml", old_field)

    with pytest.raises(
        ConfigCompatibilityError,
        match="use paths.blade_sections_dir",
    ):
        ConfigManager(config_file).load()


def test_deprecated_field_registry_reports_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = _write(
        tmp_path / "deprecated.toml",
        CURRENT_CONFIG.replace(
            'author = "Ada"',
            'author = "Ada"\nlegacy_author = "Ada"',
        ),
    )
    monkeypatch.setattr(
        ConfigManager,
        "DEPRECATED_FIELDS",
        {"defaults.legacy_author": "defaults.author"},
    )

    with pytest.raises(ConfigCompatibilityError, match="use defaults.author"):
        ConfigManager(config_file).load()
