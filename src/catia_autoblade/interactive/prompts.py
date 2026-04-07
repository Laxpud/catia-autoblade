import questionary
from pathlib import Path


def select_airfoil(files: list[str]) -> str:
    return questionary.select(
        "Select an airfoil file:",
        choices=files
    ).ask()


def select_sections(files: list[str], multi: bool = False) -> list[str]:
    if multi:
        return questionary.checkbox(
            "Select section params files (multi-select):",
            choices=files
        ).ask()
    return [questionary.select("Select a section params file:", choices=files).ask()]


def confirm_output_dir(default: str = "output") -> Path:
    path = questionary.text(
        "Output directory:",
        default=default
    ).ask()
    return Path(path)


def ask_config_value(key: str, current_value: str) -> str:
    return questionary.text(
        f"Set {key}:",
        default=current_value
    ).ask()