import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from .core.backend import BackendName, BackendError


app = typer.Typer(
    help="AutoBlade - Blade creation automation tool",
    invoke_without_command=True,
    no_args_is_help=False,
)


@dataclass(frozen=True)
class CliState:
    """一次 CLI 调用固定使用同一个配置来源，避免子命令重新发现。"""

    config_manager: object


def _get_config_manager(ctx: typer.Context):
    """独立兼容入口没有顶层 callback，因此允许回退到常规发现。"""
    from .config.manager import ConfigManager

    root = ctx.find_root()
    if isinstance(root.obj, CliState):
        return root.obj.config_manager
    return ConfigManager.discover()


def is_interactive_terminal() -> bool:
    """无参数菜单只在输入和输出都连接真实终端时启用。"""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _run_cli(action: Callable[[], object]) -> object | None:
    """统一人类可读错误、取消和进程退出码的最外层命令边界。"""
    from .interactive.prompts import PromptCancelled

    try:
        return action()
    except PromptCancelled as error:
        typer.echo(f"[INFO] {error}")
        return None
    except KeyboardInterrupt:
        typer.echo("\n[ERROR] Interrupted by user.", err=True)
        raise typer.Exit(130) from None
    except typer.Exit:
        raise
    except Exception as error:
        typer.echo(f"[ERROR] {error}", err=True)
        for note in getattr(error, "__notes__", []):
            typer.echo(f"[INFO] {note}", err=True)
        if isinstance(error, BackendError) and error.diagnostics and getattr(error, "verbose", False):
            typer.echo(error.diagnostics, err=True)
        raise typer.Exit(1) from None


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed AutoBlade version and exit.",
            is_eager=True,
        ),
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Use this configuration file instead of discovery.",
        ),
    ] = None,
) -> None:
    """Open the interactive menu when no explicit subcommand is provided."""
    if version:
        from . import __version__

        typer.echo(f"autoblade {__version__}")
        raise typer.Exit()
    from .config.manager import ConfigManager

    ctx.obj = CliState(
        ConfigManager.discover(explicit_config=config_path)
    )
    if ctx.invoked_subcommand is not None:
        return
    if not is_interactive_terminal():
        typer.echo(ctx.get_help(), err=True)
        raise typer.Exit(2)

    from .interactive.menu import run_main_menu

    _run_cli(lambda: run_main_menu(_get_config_manager(ctx)))


@app.command()
def create(
    ctx: typer.Context,
    backend: Annotated[BackendName | None, typer.Option("--backend")] = None,
    timeout_seconds: Annotated[float | None, typer.Option("--timeout-seconds", min=0.001)] = None,
    dependency_override: Annotated[Path | None, typer.Option("--freecad-dependency-dir", help="Use custom CurvesWB source; results are not certified.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    keep_failed_model: Annotated[bool, typer.Option("--keep-failed-model")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    airfoil: Annotated[str | None, typer.Option("--airfoil", "-a")] = None,
    section: Annotated[str | None, typer.Option("--section", "-s")] = None,
    output: Annotated[str | None, typer.Option("--output", "-o")] = None,
    interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False,
    keep_failed_part: Annotated[
        bool,
        typer.Option(
            "--keep-failed-part",
            help="Deprecated alias for --keep-failed-model.",
        ),
    ] = False,
    command_version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed AutoBlade version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Create one blade from one explicit model definition."""
    if command_version:
        from . import __version__

        typer.echo(f"autoblade {__version__}")
        return
    from .commands.create import run_create_command

    if keep_failed_part:
        typer.echo("[WARN] --keep-failed-part is deprecated; use --keep-failed-model.", err=True)
    _run_cli(
        lambda: run_create_command(
            airfoil,
            section,
            output,
            interactive,
            keep_failed_part or keep_failed_model,
            config_manager=_get_config_manager(ctx),
            backend=backend, timeout_seconds=timeout_seconds,
            dependency_override=dependency_override, verbose=verbose,
            dry_run=dry_run,
        )
    )


@app.command()
def batch(
    ctx: typer.Context,
    backend: Annotated[BackendName | None, typer.Option("--backend")] = None,
    timeout_seconds: Annotated[float | None, typer.Option("--timeout-seconds", min=0.001)] = None,
    dependency_override: Annotated[Path | None, typer.Option("--freecad-dependency-dir", help="Use custom CurvesWB source; results are not certified.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    keep_failed_model: Annotated[bool, typer.Option("--keep-failed-model")] = False,
    keep_failed_part: Annotated[bool, typer.Option("--keep-failed-part", help="Deprecated alias for --keep-failed-model.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    airfoil: Annotated[str | None, typer.Option("--airfoil", "-a")] = None,
    section: Annotated[str | None, typer.Option("--section", "-s")] = None,
    output: Annotated[str | None, typer.Option("--output", "-o")] = None,
    list_files: Annotated[bool, typer.Option("--list", "-l")] = False,
    interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False,
    command_version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed AutoBlade version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Build multiple closed model definitions without parameter combinations."""
    if command_version:
        from . import __version__

        typer.echo(f"autoblade {__version__}")
        return
    from .commands.batch import run_batch_command

    if keep_failed_part:
        typer.echo("[WARN] --keep-failed-part is deprecated; use --keep-failed-model.", err=True)
    _run_cli(
        lambda: run_batch_command(
            airfoil,
            section,
            output,
            list_files,
            interactive,
            config_manager=_get_config_manager(ctx),
            backend=backend, timeout_seconds=timeout_seconds,
            dependency_override=dependency_override, verbose=verbose,
            keep_failed_part=keep_failed_part or keep_failed_model,
            dry_run=dry_run,
        )
    )


@app.command()
def sweep(
    ctx: typer.Context,
    backend: Annotated[BackendName | None, typer.Option("--backend")] = None,
    timeout_seconds: Annotated[float | None, typer.Option("--timeout-seconds", min=0.001)] = None,
    dependency_override: Annotated[Path | None, typer.Option("--freecad-dependency-dir", help="Use custom CurvesWB source; results are not certified.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    keep_failed_model: Annotated[bool, typer.Option("--keep-failed-model")] = False,
    keep_failed_part: Annotated[bool, typer.Option("--keep-failed-part", help="Deprecated alias for --keep-failed-model.")] = False,
    airfoils: Annotated[
        list[str],
        typer.Option(
            "--airfoil",
            "-a",
            help="Explicit airfoil CSV basename; repeat for multiple values.",
        ),
    ] = [],
    sections: Annotated[
        list[str],
        typer.Option(
            "--section",
            "-s",
            help="Explicit six-column template; repeat for multiple values.",
        ),
    ] = [],
    output: Annotated[str | None, typer.Option("--output", "-o")] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print the complete stable manifest without starting CAD.",
        ),
    ] = False,
    interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False,
) -> None:
    """Build an explicit Cartesian product of airfoils and section templates."""
    from .commands.sweep import run_sweep_command

    if keep_failed_part:
        typer.echo("[WARN] --keep-failed-part is deprecated; use --keep-failed-model.", err=True)
    _run_cli(
        lambda: run_sweep_command(
            airfoils,
            sections,
            output,
            dry_run,
            interactive,
            config_manager=_get_config_manager(ctx),
            backend=backend, timeout_seconds=timeout_seconds,
            dependency_override=dependency_override, verbose=verbose,
            keep_failed_part=keep_failed_part or keep_failed_model,
        )
    )


@app.command("list")
def list_inputs(
    ctx: typer.Context,
    config_show: Annotated[bool, typer.Option("--config")] = False,
) -> None:
    """List available files or configuration."""
    from .commands.list import run_list_command

    _run_cli(
        lambda: run_list_command(
            config_show,
            config_manager=_get_config_manager(ctx),
        )
    )


@app.command()
def config(
    ctx: typer.Context,
    action: Annotated[str, typer.Argument()] = ...,
    key: Annotated[str | None, typer.Option("--key", "-k")] = None,
    value: Annotated[str | None, typer.Option("--value", "-v")] = None,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Apply a previewed schema migration and create a backup.",
        ),
    ] = False,
) -> None:
    """Manage configuration file (show, set, reset, migrate)."""
    if action not in {"show", "set", "reset", "migrate"}:
        raise typer.BadParameter(
            "action must be one of: show, set, reset, migrate"
        )
    if action == "set" and (key is None or value is None):
        raise typer.BadParameter(
            "config set requires both --key and --value"
        )
    if apply and action != "migrate":
        raise typer.BadParameter("--apply is only valid for config migrate")

    from .commands.config import run_config_command

    _run_cli(
        lambda: run_config_command(
            action,
            key,
            value,
            apply,
            config_manager=_get_config_manager(ctx),
        )
    )


@app.command("init")
def initialize_workspace(
    target: Annotated[
        Path,
        typer.Argument(help="Explicit directory for the new modeling workspace."),
    ],
    with_examples: Annotated[
        bool,
        typer.Option(help="Copy the validated blade example and dependencies."),
    ] = False,
    with_airfoil_library: Annotated[
        bool,
        typer.Option(
            help="Copy the complete audited built-in airfoil library."
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(help="Replace only managed template files after preview."),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option("--interactive", "-i", help="Confirm managed-file conflicts."),
    ] = False,
) -> None:
    """Create an editable workspace outside the installed package."""
    from .commands.initialize import run_init_command

    _run_cli(
        lambda: run_init_command(
            target,
            with_examples=with_examples,
            with_airfoil_library=with_airfoil_library,
            force=force,
            interactive=interactive,
        )
    )


@app.command()
def doctor(
    ctx: typer.Context,
    backend: Annotated[BackendName | None, typer.Option("--backend")] = None,
    all_backends: Annotated[bool, typer.Option("--all")] = False,
) -> None:
    """Diagnose the installation without starting or attaching to CATIA."""
    from .commands.doctor import run_doctor_command

    _run_cli(
        lambda: run_doctor_command(
            config_manager=_get_config_manager(ctx), backend=backend, all_backends=all_backends,
        )
    )


def create_entrypoint() -> None:
    """运行与 ``autoblade create`` 参数一致的独立 CLI 入口。"""
    # console script 会零参数调用目标函数，因此需要先由 Typer 解析命令行，
    # 再复用主命令的回调，避免独立入口与子命令维护两套参数契约。
    typer.run(create)


def batch_entrypoint() -> None:
    """运行与 ``autoblade batch`` 参数一致的独立 CLI 入口。"""
    # 与 create 入口采用同一模式，保证新增或调整选项时两种调用方式同步变化。
    typer.run(batch)


if __name__ == "__main__":
    app()
