import os
from pathlib import Path
from typing import Tuple


def get_available_files(input_dir: str = "input") -> Tuple[list[str], list[str]]:
    airfoil_files = []
    section_params_files = []

    airfoil_dir = os.path.join(input_dir, "airfoils")
    if os.path.exists(airfoil_dir):
        for f in os.listdir(airfoil_dir):
            if f.endswith(".csv"):
                airfoil_files.append(f)

    section_params_dir = os.path.join(input_dir, "section_params")
    if os.path.exists(section_params_dir):
        for f in os.listdir(section_params_dir):
            if f.endswith(".csv"):
                section_params_files.append(f)
        section_params_files.sort()

    return airfoil_files, section_params_files