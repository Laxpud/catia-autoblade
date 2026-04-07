from ..config.manager import ConfigManager


def run_config_command(action: str, key: str | None, value: str | None):
    manager = ConfigManager()

    if action == "show":
        config = manager.load()
        print("[INFO] Current configuration:")
        print(f"  input_dir: {config.paths.input_dir}")
        print(f"  output_dir: {config.paths.output_dir}")
        print(f"  airfoil_dir: {config.paths.airfoil_dir}")
        print(f"  section_params_dir: {config.paths.section_params_dir}")
        print(f"  author: {config.defaults.author}")
        print(f"  output_name_template: {config.defaults.output_name_template}")

    elif action == "set":
        if not key or not value:
            print("[ERROR] Both key and value are required for 'set' action.")
            return

        valid_keys = ["input_dir", "output_dir", "airfoil_dir", "section_params_dir", "author", "output_name_template"]
        if key not in valid_keys:
            print(f"[ERROR] Invalid key '{key}'. Valid keys: {', '.join(valid_keys)}")
            return

        config = manager.load()
        if hasattr(config.paths, key):
            setattr(config.paths, key, value)
        elif hasattr(config.defaults, key):
            setattr(config.defaults, key, value)
        manager.save(config)
        print(f"[INFO] {key} set to '{value}'")

    elif action == "reset":
        manager.save(manager.load().__class__())
        print("[INFO] Configuration reset to defaults.")