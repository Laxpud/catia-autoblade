from ..utils.file_scanner import get_available_files


def run_list_command(config_show: bool):
    if config_show:
        from ..config.manager import ConfigManager
        manager = ConfigManager()
        config = manager.load()
        print("[INFO] Current configuration:")
        print(f"  input_dir: {config.paths.input_dir}")
        print(f"  output_dir: {config.paths.output_dir}")
        print(f"  airfoil_dir: {config.paths.airfoil_dir}")
        print(f"  section_params_dir: {config.paths.section_params_dir}")
        print(f"  author: {config.defaults.author}")
        print(f"  output_name_template: {config.defaults.output_name_template}")
    else:
        airfoil_files, section_params_files = get_available_files()
        print("[INFO] Available airfoil files:")
        for f in airfoil_files:
            print(f"  - {f}")
        print("\n[INFO] Available section params files:")
        for f in section_params_files:
            print(f"  - {f}")
        print(f"\n[INFO] Total combinations: {len(airfoil_files)} x {len(section_params_files)} = {len(airfoil_files) * len(section_params_files)}")