import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from ..utils.file_scanner import get_available_files


def run_create_command(
    airfoil: str | None,
    section: str | None,
    output: str | None,
    interactive: bool,
):
    if interactive:
        from ..interactive.prompts import select_airfoil, select_sections, confirm_output_dir
        airfoil_files, section_params_files = get_available_files()

        if not airfoil_files:
            print("[ERROR] No airfoil files found.")
            return

        if not section_params_files:
            print("[ERROR] No section params files found.")
            return

        selected_airfoil = select_airfoil(airfoil_files)
        selected_section = select_sections(section_params_files, multi=False)[0]
        output_dir = confirm_output_dir(output or "output")
    else:
        airfoil_files, section_params_files = get_available_files()

        if not airfoil_files:
            print("[ERROR] No airfoil files found.")
            return

        if not section_params_files:
            print("[ERROR] No section params files found.")
            return

        selected_airfoil = airfoil if airfoil else airfoil_files[0]
        selected_section = section if section else section_params_files[0]
        output_dir = output or "output"

    if selected_airfoil not in airfoil_files:
        print(f"[ERROR] Airfoil file '{selected_airfoil}' not found.")
        return

    if selected_section not in section_params_files:
        print(f"[ERROR] Section params file '{selected_section}' not found.")
        return

    print(f"\n[INFO] Creating single blade...")
    print(f"[INFO] Airfoil: {selected_airfoil}, Section: {selected_section}")

    from ..core.create_blade import create_single_blade
    airfoil_name = os.path.splitext(selected_airfoil)[0]
    param_idx = os.path.splitext(selected_section)[0].replace("section_params-", "")
    output_name = f"{airfoil_name}_blade-{param_idx}"

    try:
        create_single_blade(selected_airfoil, selected_section, output_dir, output_name)
        print(f"[SUCCESS] Blade created: {output_name}")
    except Exception as e:
        print(f"[ERROR] Failed to create blade: {e}")