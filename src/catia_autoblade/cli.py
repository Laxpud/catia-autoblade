import typer
from typing import Optional, Annotated

app = typer.Typer(help="CATIA AutoBlade - Blade creation automation tool")


@app.command()
def create(
    airfoil: Annotated[Optional[str], typer.Option("--airfoil", "-a")] = None,
    section: Annotated[Optional[str], typer.Option("--section", "-s")] = None,
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
    interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False,
):
    """Create a single blade"""
    from .commands.create import run_create_command
    run_create_command(airfoil, section, output, interactive)


@app.command()
def batch(
    airfoil: Annotated[Optional[str], typer.Option("--airfoil", "-a")] = None,
    section: Annotated[Optional[str], typer.Option("--section", "-s")] = None,
    output: Annotated[Optional[str], typer.Option("--output", "-o")] = None,
    list_files: Annotated[bool, typer.Option("--list", "-l")] = False,
    interactive: Annotated[bool, typer.Option("--interactive", "-i")] = False,
):
    """Batch create blades"""
    from .commands.batch import run_batch_command
    run_batch_command(airfoil, section, output, list_files, interactive)


@app.command()
def list(
    config_show: Annotated[bool, typer.Option("--config")] = False,
):
    """List available files or configuration"""
    from .commands.list import run_list_command
    run_list_command(config_show)


@app.command()
def config(
    action: Annotated[str, typer.Argument] = ...,
    key: Annotated[Optional[str], typer.Option("--key", "-k")] = None,
    value: Annotated[Optional[str], typer.Option("--value", "-v")] = None,
):
    """Manage configuration file (show, set, reset)"""
    if action not in ["show", "set", "reset"]:
        raise typer.BadParameter("action must be one of: show, set, reset")
    from .commands.config import run_config_command
    run_config_command(action, key, value)


if __name__ == "__main__":
    app()