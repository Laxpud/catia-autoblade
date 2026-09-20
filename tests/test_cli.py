import typer
import pytest
from click import unstyle
from typer.testing import CliRunner

from autoblade import cli
from autoblade.commands import batch as batch_commands
from autoblade.commands import config as config_commands
from autoblade.commands import create as create_commands
from autoblade.commands import doctor as doctor_commands
from autoblade.commands import initialize as initialize_commands
from autoblade.commands import list as list_commands
from autoblade.commands import sweep as sweep_commands
from autoblade.config.manager import ConfigManager
from autoblade.config.settings import AppConfig
from autoblade.interactive import menu
from autoblade.interactive.prompts import PromptCancelled


runner = CliRunner()


def test_version_reports_package_version_without_opening_menu(monkeypatch) -> None:
    monkeypatch.setattr(cli, "is_interactive_terminal", lambda: True)
    called = []
    monkeypatch.setattr(menu, "run_main_menu", lambda: called.append(True))

    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "autoblade 0.2.0"
    assert called == []


def test_create_subcommand_parses_short_options(monkeypatch) -> None:
    calls = []

    def fake_run(
        airfoil,
        section,
        output,
        interactive,
        keep_failed_part,
        **kwargs,
    ):
        calls.append(
            (airfoil, section, output, interactive, keep_failed_part)
        )

    monkeypatch.setattr(create_commands, "run_create_command", fake_run)
    result = runner.invoke(
        cli.app,
        [
            "create",
            "-a",
            "foil.csv",
            "-s",
            "sections.csv",
            "-o",
            "generated",
            "-i",
            "--keep-failed-part",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        ("foil.csv", "sections.csv", "generated", True, True)
    ]


def test_batch_subcommand_parses_all_options(monkeypatch) -> None:
    calls = []

    def fake_run(airfoil, section, output, list_files, interactive, **kwargs):
        calls.append((airfoil, section, output, list_files, interactive))

    monkeypatch.setattr(batch_commands, "run_batch_command", fake_run)
    result = runner.invoke(
        cli.app,
        [
            "batch",
            "--airfoil",
            "foil.csv",
            "--section",
            "sections.csv",
            "--output",
            "generated",
            "--list",
            "--interactive",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        ("foil.csv", "sections.csv", "generated", True, True)
    ]


def test_sweep_subcommand_parses_repeatable_explicit_selections(
    monkeypatch,
) -> None:
    calls = []

    def fake_run(airfoils, sections, output, dry_run, interactive, **kwargs):
        calls.append((airfoils, sections, output, dry_run, interactive))

    monkeypatch.setattr(sweep_commands, "run_sweep_command", fake_run)
    result = runner.invoke(
        cli.app,
        [
            "sweep",
            "--airfoil",
            "foil-b.csv",
            "--airfoil",
            "foil-a.csv",
            "--section",
            "blade_sections-2.csv",
            "--section",
            "blade_sections-1.csv",
            "--output",
            "generated",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        (
            ["foil-b.csv", "foil-a.csv"],
            ["blade_sections-2.csv", "blade_sections-1.csv"],
            "generated",
            True,
            False,
        )
    ]


def test_list_subcommand_parses_config_flag(monkeypatch) -> None:
    calls = []
    def fake_run(config_show, **kwargs):
        calls.append(config_show)

    monkeypatch.setattr(list_commands, "run_list_command", fake_run)

    result = runner.invoke(cli.app, ["list", "--config"])

    assert result.exit_code == 0, result.output
    assert calls == [True]


def test_config_subcommand_parses_action_key_and_value(monkeypatch) -> None:
    calls = []

    def fake_run(action, key, value, apply, **kwargs):
        calls.append((action, key, value))

    monkeypatch.setattr(config_commands, "run_config_command", fake_run)
    result = runner.invoke(
        cli.app,
        ["config", "set", "--key", "output_dir", "--value", "generated"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [("set", "output_dir", "generated")]


def test_config_migrate_apply_is_forwarded(monkeypatch) -> None:
    calls = []

    def fake_run(action, key, value, apply, **kwargs):
        calls.append((action, key, value, apply))

    monkeypatch.setattr(config_commands, "run_config_command", fake_run)

    result = runner.invoke(cli.app, ["config", "migrate", "--apply"])

    assert result.exit_code == 0, result.output
    assert calls == [("migrate", None, None, True)]


def test_config_migrate_apply_creates_backup_through_cli(tmp_path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        r'''version = "1.0.0"
[paths]
input_dir = "input"
output_dir = "output"
airfoil_dir = 'input\airfoils'
blade_sections_dir = 'input\blade_sections'
[defaults]
author = ""
output_name_template = "{blade}"
''',
        encoding="utf-8",
    )

    preview = runner.invoke(
        cli.app,
        ["--config", str(config_file), "config", "migrate"],
    )
    applied = runner.invoke(
        cli.app,
        ["--config", str(config_file), "config", "migrate", "--apply"],
    )

    assert preview.exit_code == 0, preview.output
    assert "Preview only" in preview.stdout
    assert applied.exit_code == 0, applied.output
    assert "Backup created" in applied.stdout
    assert 'version = "4.0.0"' in config_file.read_text(encoding="utf-8")
    assert (tmp_path / "config.toml.v1.0.0.bak").is_file()


def test_invalid_config_action_is_rejected_before_handler(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(config_commands, "run_config_command", calls.append)

    result = runner.invoke(cli.app, ["config", "invalid"])

    assert result.exit_code == 2
    assert "action must be one of" in result.output
    assert calls == []


def test_standalone_create_signature_matches_main_callback(monkeypatch) -> None:
    callbacks = []
    monkeypatch.setattr(cli.typer, "run", callbacks.append)

    cli.create_entrypoint()

    assert callbacks == [cli.create]


def test_standalone_batch_signature_matches_main_callback(monkeypatch) -> None:
    callbacks = []
    monkeypatch.setattr(cli.typer, "run", callbacks.append)

    cli.batch_entrypoint()

    assert callbacks == [cli.batch]


def test_standalone_callback_parses_same_create_options(monkeypatch) -> None:
    calls = []

    def fake_run(
        airfoil,
        section,
        output,
        interactive,
        keep_failed_part,
        **kwargs,
    ):
        calls.append(
            (airfoil, section, output, interactive, keep_failed_part)
        )

    monkeypatch.setattr(create_commands, "run_create_command", fake_run)
    standalone_app = typer.Typer()
    standalone_app.command()(cli.create)

    result = runner.invoke(
        standalone_app,
        ["--airfoil", "foil.csv", "--section", "sections.csv"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [("foil.csv", "sections.csv", None, False, False)]


@pytest.mark.parametrize("callback", [cli.create, cli.batch])
def test_standalone_entrypoints_report_version(callback) -> None:
    standalone_app = typer.Typer()
    standalone_app.command()(callback)

    result = runner.invoke(standalone_app, ["--version"])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "autoblade 0.2.0"


def test_global_explicit_config_is_forwarded_to_commands(
    tmp_path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "custom.toml"
    config_file.write_text('version = "4.0.0"', encoding="utf-8")
    calls = []

    def fake_run(config_show, *, config_manager):
        calls.append((config_show, config_manager))

    monkeypatch.setattr(list_commands, "run_list_command", fake_run)

    result = runner.invoke(
        cli.app,
        ["--config", str(config_file), "list"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0][0] is False
    assert calls[0][1].source.kind == "explicit"
    assert calls[0][1].config_file == config_file.resolve()


def test_init_subcommand_requires_explicit_target_and_forwards_options(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []

    def fake_run(
        target,
        *,
        with_examples,
        with_airfoil_library,
        force,
        interactive,
    ):
        calls.append(
            (
                target,
                with_examples,
                with_airfoil_library,
                force,
                interactive,
            )
        )

    monkeypatch.setattr(initialize_commands, "run_init_command", fake_run)

    missing = runner.invoke(cli.app, ["init"])
    result = runner.invoke(
        cli.app,
        [
            "init",
            str(tmp_path / "workspace"),
            "--with-examples",
            "--with-airfoil-library",
            "--force",
        ],
    )

    assert missing.exit_code == 2
    assert result.exit_code == 0, result.output
    assert calls == [
        (tmp_path / "workspace", True, True, True, False)
    ]


def test_doctor_subcommand_uses_discovered_config(monkeypatch) -> None:
    calls = []

    def fake_run(*, config_manager, backend, all_backends):
        calls.append(config_manager)

    monkeypatch.setattr(doctor_commands, "run_doctor_command", fake_run)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError("missing input"), "missing input"),
        (ValueError("invalid config"), "invalid config"),
        (RuntimeError("CATIA modeling failed"), "CATIA modeling failed"),
    ],
)
def test_domain_and_execution_errors_exit_one_on_stderr(
    error: Exception,
    message: str,
    monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(create_commands, "run_create_command", fail)

    result = runner.invoke(
        cli.app,
        ["create", "--section", "sections.csv"],
    )

    assert result.exit_code == 1
    assert message in result.stderr
    assert "[ERROR]" in result.stderr


def test_typer_usage_error_exits_two() -> None:
    result = runner.invoke(cli.app, ["create", "--unknown-option"])

    assert result.exit_code == 2
    assert "No such option" in result.output


def test_config_set_missing_value_is_usage_error() -> None:
    result = runner.invoke(
        cli.app,
        ["config", "set", "--key", "output_dir"],
    )

    assert result.exit_code == 2
    assert "requires both --key and --value" in unstyle(result.output)


def test_missing_repository_file_exits_one_on_stderr(
    tmp_path,
    monkeypatch,
) -> None:
    config = AppConfig()
    config.paths.input_dir = tmp_path / "input"
    config.paths.output_dir = tmp_path / "output"
    config.paths.airfoil_dir = tmp_path / "input" / "airfoils"
    config.paths.blade_sections_dir = tmp_path / "input" / "sections"
    config.paths.airfoil_dir.mkdir(parents=True)
    config.paths.blade_sections_dir.mkdir(parents=True)
    manager = ConfigManager(tmp_path / "config.toml")
    manager.save(config)
    result = runner.invoke(
        cli.app,
        [
            "--config",
            str(manager.config_file),
            "create",
            "--airfoil",
            "missing.csv",
            "--section",
            "missing.csv",
        ],
    )

    assert result.exit_code == 1
    assert "No blade section definition files were found" in result.stderr


def test_invalid_toml_config_exits_one_on_stderr(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("version = [", encoding="utf-8")
    manager = ConfigManager(config_file)
    result = runner.invoke(
        cli.app,
        [
            "--config",
            str(manager.config_file),
            "create",
            "--section",
            "sections.csv",
        ],
    )

    assert result.exit_code == 1
    assert "[ERROR]" in result.stderr


def test_keyboard_interrupt_exits_130(monkeypatch) -> None:
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(create_commands, "run_create_command", interrupt)

    result = runner.invoke(
        cli.app,
        ["create", "--section", "sections.csv"],
    )

    assert result.exit_code == 130
    assert "Interrupted by user" in result.stderr


def test_interactive_cancel_is_a_successful_command_cancel(monkeypatch) -> None:
    def cancel(*args, **kwargs):
        raise PromptCancelled("Build was cancelled before CATIA started.")

    monkeypatch.setattr(create_commands, "run_create_command", cancel)

    result = runner.invoke(cli.app, ["create", "--interactive"])

    assert result.exit_code == 0
    assert "cancelled before CATIA started" in result.stdout


def test_no_argument_non_tty_shows_help_and_exits_two(monkeypatch) -> None:
    monkeypatch.setattr(cli, "is_interactive_terminal", lambda: False)
    called = []
    monkeypatch.setattr(
        menu,
        "run_main_menu",
        lambda config_manager=None: called.append(True),
    )

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 2
    assert "Usage:" in result.output
    assert called == []


def test_no_argument_tty_opens_menu_and_exits_zero(monkeypatch) -> None:
    monkeypatch.setattr(cli, "is_interactive_terminal", lambda: True)
    called = []
    monkeypatch.setattr(
        menu,
        "run_main_menu",
        lambda config_manager=None: called.append(True),
    )

    result = runner.invoke(cli.app, [])

    assert result.exit_code == 0, result.output
    assert called == [True]


def test_main_menu_returns_after_action_until_exit(monkeypatch) -> None:
    actions = iter(["create", "exit"])
    calls = []
    monkeypatch.setattr(
        "autoblade.interactive.prompts.select_main_action",
        lambda: next(actions),
    )
    monkeypatch.setattr(
        menu,
        "_run_menu_action",
        lambda action, **kwargs: calls.append(action),
    )

    menu.run_main_menu()

    assert calls == ["create"]


def test_main_menu_cancel_returns_to_parent_menu(monkeypatch) -> None:
    actions = iter(["create", "list", "exit"])
    calls = []
    monkeypatch.setattr(
        "autoblade.interactive.prompts.select_main_action",
        lambda: next(actions),
    )

    def run_action(action, **kwargs):
        calls.append(action)
        if action == "create":
            raise PromptCancelled("Current operation cancelled.")

    monkeypatch.setattr(menu, "_run_menu_action", run_action)

    menu.run_main_menu()

    assert calls == ["create", "list"]
