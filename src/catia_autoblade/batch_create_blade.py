import os
import sys
import argparse

from .create_blade import create_single_blade

def get_available_files(input_dir="input"):
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

def batch_create_blades(airfoil_files=None, section_params_files=None, output_base_dir="output"):
    if airfoil_files is None:
        airfoil_files, _ = get_available_files()
    if section_params_files is None:
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

def main():
    parser = argparse.ArgumentParser(description="Batch create blade models in CATIA")
    parser.add_argument("--airfoil", type=str, default=None, help="Specific airfoil CSV file (e.g., sc1095.csv)")
    parser.add_argument("--section", type=str, default=None, help="Specific section params CSV file (e.g., section_params_1.csv)")
    parser.add_argument("--list", action="store_true", help="List available airfoil and section params files")
    parser.add_argument("--output", type=str, default="output", help="Output base directory")

    args = parser.parse_args()

    airfoil_files, section_params_files = get_available_files()

    if args.list:
        print("[INFO] Available airfoil files:")
        for f in airfoil_files:
            print(f"  - {f}")
        print("\n[INFO] Available section params files:")
        for f in section_params_files:
            print(f"  - {f}")
        print(f"\n[INFO] Total combinations: {len(airfoil_files)} x {len(section_params_files)} = {len(airfoil_files) * len(section_params_files)}")
        sys.exit(0)

    airfoil_list = None
    section_list = None

    if args.airfoil:
        airfoil_list = [args.airfoil] if args.airfoil in airfoil_files else []
        if not airfoil_list:
            print(f"[ERROR] Airfoil file '{args.airfoil}' not found.")
            sys.exit(1)

    if args.section:
        section_list = [args.section] if args.section in section_params_files else []
        if not section_list:
            print(f"[ERROR] Section params file '{args.section}' not found.")
            sys.exit(1)

    print(f"[INFO] Starting batch processing...")
    results = batch_create_blades(airfoil_list, section_list, args.output)

    success_count = len([r for r in results if r['status'] == 'success'])
    print(f"\n[INFO] Batch completed: {success_count}/{len(results)} successful.")

    for r in results:
        if r['status'] == 'failed':
            print(f"  [FAILED] {r['airfoil']} + {r['section']}: {r.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main()
