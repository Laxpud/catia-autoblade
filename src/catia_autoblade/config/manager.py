import tomlkit
from pathlib import Path
from .settings import AppConfig


class ConfigManager:
    CONFIG_FILE = Path("config.toml")

    def load(self) -> AppConfig:
        if not self.CONFIG_FILE.exists():
            return AppConfig()
        with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
            data = tomlkit.load(f)
        return AppConfig.model_validate(data)

    def save(self, config: AppConfig) -> None:
        data = config.model_dump()
        for section in ["paths"]:
            if section in data and isinstance(data[section], dict):
                for key, value in data[section].items():
                    if isinstance(value, Path):
                        data[section][key] = str(value)
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            tomlkit.dump(data, f)

    def update_paths(self, **kwargs) -> None:
        config = self.load()
        for key, value in kwargs.items():
            setattr(config.paths, key, Path(value) if value else None)
        self.save(config)