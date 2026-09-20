import typer

from ..config.manager import ConfigManager


CONFIG_KEYS = (
    "input_dir",
    "output_dir",
    "airfoil_dir",
    "blade_sections_dir",
    "backend",
    "timeout_seconds",
    "author",
    "output_name_template",
)


def run_config_command(
    action: str,
    key: str | None,
    value: str | None,
    apply: bool = False,
    *,
    config_manager: ConfigManager | None = None,
) -> None:
    manager = config_manager or ConfigManager()

    if action == "show":
        config = manager.load()
        typer.echo("[INFO] Current configuration:")
        typer.echo(f"  source: {manager.source_description}")
        typer.echo(f"  version: {config.version}")
        typer.echo(f"  input_dir: {config.paths.input_dir}")
        typer.echo(f"  output_dir: {config.paths.output_dir}")
        typer.echo(f"  airfoil_dir: {config.paths.airfoil_dir}")
        typer.echo(f"  blade_sections_dir: {config.paths.blade_sections_dir}")
        typer.echo(f"  backend: {config.defaults.backend.value}")
        typer.echo(f"  timeout_seconds: {config.freecad.timeout_seconds:g}")
        typer.echo(f"  freecad.launcher: {config.freecad.launcher}")
        typer.echo(f"  freecad.app_id: {config.freecad.app_id}")
        typer.echo(f"  author: {config.defaults.author}")
        typer.echo(
            "  output_name_template: "
            f"{config.defaults.output_name_template}"
        )
        return

    if action == "migrate":
        plan = manager.plan_migration()
        if plan is None:
            typer.echo(
                f"[INFO] Configuration already uses schema "
                f"{manager.CURRENT_SCHEMA_VERSION}: {manager.config_file}"
            )
            return
        typer.echo("[INFO] Configuration migration preview:")
        typer.echo(
            f"  schema: {plan.source_version} -> {plan.target_version}"
        )
        typer.echo(f"  source file: {plan.config_file}")
        typer.echo(f"  target file: {plan.target_config_file}")
        for change in plan.changes:
            typer.echo(
                f"  {change.field}: {change.before!r} -> {change.after!r} "
                f"({change.reason})"
            )
        if not apply:
            typer.echo(
                "[INFO] Preview only; rerun with --apply to write a backup "
                "and migrate."
            )
            return
        backup = manager.apply_migration(plan)
        typer.echo(f"[SUCCESS] Configuration migrated: {manager.config_file}")
        typer.echo(f"[INFO] Backup created: {backup}")
        return

    if action == "set":
        if key is None or value is None:
            raise ValueError("Both --key and --value are required for config set.")
        if key not in CONFIG_KEYS:
            raise ValueError(
                f"Invalid configuration key {key!r}. Valid keys: "
                f"{', '.join(CONFIG_KEYS)}"
            )

        config = manager.load()
        owner = (config.freecad if key == "timeout_seconds" else
                 config.paths if hasattr(config.paths, key) else config.defaults)
        setattr(owner, key, value)
        manager.save(config)
        typer.echo(f"[INFO] {key} set to {value!r}")
        return

    if action == "reset":
        manager.save(manager.load().__class__())
        typer.echo("[INFO] Configuration reset to defaults.")
        return

    raise ValueError("Configuration action must be one of: show, set, reset, migrate.")
