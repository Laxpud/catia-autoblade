import os

from .create_blade import create_single_blade


def batch_create_blades(airfoil_files=None, section_params_files=None, output_base_dir="output"):
    if airfoil_files is None:
        from ..utils.file_scanner import get_available_files
        airfoil_files, _ = get_available_files()
    if section_params_files is None:
        from ..utils.file_scanner import get_available_files
        _, section_params_files = get_available_files()

    airfoil_files = [f for f in airfoil_files if f.endswith(".csv")]

    print(f"[INFO] Batch processing: {len(airfoil_files)} airfoil(s) x {len(section_params_files)} section param(s) = {len(airfoil_files) * len(section_params_files)} blade(s)")

    results = []
    for airfoil_file in airfoil_files:
        for section_file in section_params_files:
            try:
                print(f"\n{'='*60}")
                print(f"[INFO] Creating blade: airfoil={airfoil_file}, section={section_file}")
                airfoil_name = os.path.splitext(airfoil_file)[0]
                param_file_idx = os.path.splitext(section_file)[0].replace("section_params-", "")
                output_name = f"{airfoil_name}_blade-{param_file_idx}"
                output_dir = os.path.join(output_base_dir, f"{airfoil_name}")
                create_single_blade(airfoil_file, section_file, output_dir, output_name)
                results.append({"status": "success", "airfoil": airfoil_file, "section": section_file, "output": output_dir})
                print(f"[SUCCESS] Blade created: {output_name}")
            except Exception as e:
                results.append({"status": "failed", "airfoil": airfoil_file, "section": section_file, "error": str(e)})
                print(f"[ERROR] Failed to create blade: {e}")

    print(f"\n{'='*60}")
    print(f"[INFO] Batch processing completed. {len([r for r in results if r['status'] == 'success'])}/{len(results)} successful.")
    return results