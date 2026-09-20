from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
from typing import Any, ClassVar, Mapping
from uuid import uuid4
import warnings

from pydantic import ValidationError
import tomlkit

from .settings import AppConfig, CURRENT_CONFIG_SCHEMA_VERSION


LEGACY_CONFIG_SCHEMA_VERSION = "1.0.0"
PREVIOUS_CONFIG_SCHEMA_VERSION = "2.0.0"


class ConfigCompatibilityError(ValueError):
    """配置 schema 无法由当前程序安全解释。"""


class ConfigMigrationRequiredError(ConfigCompatibilityError):
    """写操作被旧 schema 阻止，必须先显式迁移。"""


class ConfigMigrationWarning(UserWarning):
    """配置可读取，但存在应由用户显式应用的迁移。"""


@dataclass(frozen=True)
class ConfigMigrationChange:
    """单项迁移变化；字段值保持可展示，不包含输入或输出文件内容。"""

    field: str
    before: str
    after: str
    reason: str


@dataclass(frozen=True)
class ConfigMigrationPlan:
    """经过验证、可在原文件未变化时安全应用的迁移计划。"""

    config_file: Path
    target_config_file: Path
    source_version: str
    target_version: str
    changes: tuple[ConfigMigrationChange, ...]
    original_sha256: str
    migrated_text: str


@dataclass(frozen=True)
class ConfigSource:
    """配置发现结果；内置默认值仍记录其路径解析基准。"""

    kind: str
    path: Path


class ConfigManager:
    """发现、校验和加载配置，并安全处理持久化 schema。"""

    CONFIG_FILE = Path("config.toml")
    USER_CONFIG_DIR = "autoblade"
    LEGACY_USER_CONFIG_DIR = "catia-autoblade"
    CURRENT_SCHEMA_VERSION = CURRENT_CONFIG_SCHEMA_VERSION
    LEGACY_SCHEMA_VERSIONS = frozenset(
        {
            LEGACY_CONFIG_SCHEMA_VERSION,
            PREVIOUS_CONFIG_SCHEMA_VERSION,
            "unversioned",
            "3.0.0",
        }
    )
    # 只有真实移除字段时才向此表增加条目。迁移器会在通用 unknown-field
    # 错误之前给出替代字段，避免维护者为了假设场景预建迁移类层次。
    DEPRECATED_FIELDS: ClassVar[Mapping[str, str]] = {
        "paths.section_params_dir": "paths.blade_sections_dir",
    }

    def __init__(
        self,
        config_file: str | Path | None = None,
        *,
        source_kind: str | None = None,
        migration_target_file: str | Path | None = None,
    ) -> None:
        if config_file is None:
            discovered = self.discover()
            self.config_file = discovered.config_file
            self.source = discovered.source
            self._migration_target_file = discovered._migration_target_file
            return

        # 相对配置文件名以创建管理器时的工作目录为基准；先固化为绝对路径，
        # 后续即使交互流程改变工作目录，配置解析基准也不会漂移。
        self.config_file = Path(config_file).expanduser().resolve()
        self.source = ConfigSource(source_kind or "explicit", self.config_file)
        self._migration_target_file = (
            Path(migration_target_file).expanduser().resolve()
            if migration_target_file is not None
            else None
        )

    @classmethod
    def discover(
        cls,
        explicit_config: str | Path | None = None,
        *,
        working_dir: str | Path | None = None,
        user_config_file: str | Path | None = None,
        legacy_user_config_file: str | Path | None = None,
    ) -> ConfigManager:
        """按显式路径、工作区、新用户目录、旧目录 fallback、默认值发现。"""
        base_dir = Path(working_dir or Path.cwd()).expanduser().resolve()
        if explicit_config is not None:
            candidate = Path(explicit_config).expanduser()
            if not candidate.is_absolute():
                candidate = base_dir / candidate
            return cls(candidate.resolve(), source_kind="explicit")

        workspace_config = (base_dir / cls.CONFIG_FILE).resolve()
        if workspace_config.is_file():
            return cls(workspace_config, source_kind="workspace")

        user_config = Path(
            user_config_file or cls.default_user_config_file()
        ).expanduser().resolve()
        if user_config.is_file():
            return cls(user_config, source_kind="user")

        # 测试或嵌入调用显式覆盖新用户路径时，不应意外读取真实主目录中的旧配置；
        # 调用方若要验证 fallback，必须同时传入对应的旧路径。
        legacy_user_config = None
        if legacy_user_config_file is not None:
            legacy_user_config = Path(legacy_user_config_file).expanduser().resolve()
        elif user_config_file is None:
            legacy_user_config = cls.default_legacy_user_config_file().resolve()
        if legacy_user_config is not None and legacy_user_config.is_file():
            warnings.warn(
                "Using legacy user configuration at "
                f"{legacy_user_config} because the canonical AutoBlade path "
                f"{user_config} does not exist. Run 'autoblade config migrate' "
                "to preview the location migration.",
                ConfigMigrationWarning,
                stacklevel=2,
            )
            return cls(
                legacy_user_config,
                source_kind="legacy-user",
                migration_target_file=user_config,
            )

        # 内置默认路径以启动目录为基准，但不会在那里创建 config.toml；只有
        # init、config set/reset/migrate 等显式写命令能够持久化用户文件。
        return cls(workspace_config, source_kind="defaults")

    @classmethod
    def default_user_config_file(cls) -> Path:
        """返回平台惯例下的用户级配置路径，不创建任何目录。"""
        if os.name == "nt":
            base_dir = Path(
                os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            )
        else:
            base_dir = Path(
                os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
            )
        return base_dir / cls.USER_CONFIG_DIR / cls.CONFIG_FILE

    @classmethod
    def default_legacy_user_config_file(cls) -> Path:
        """返回旧产品目录中的用户配置路径，不创建或修改任何文件。"""
        if os.name == "nt":
            base_dir = Path(
                os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            )
        else:
            base_dir = Path(
                os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
            )
        return base_dir / cls.LEGACY_USER_CONFIG_DIR / cls.CONFIG_FILE

    @property
    def source_description(self) -> str:
        if self.source.kind == "defaults":
            return f"built-in defaults (base: {self.config_file.parent})"
        if self.source.kind == "legacy-user":
            return f"legacy user fallback: {self.config_file}"
        return f"{self.source.kind}: {self.config_file}"

    def load(self) -> AppConfig:
        """读取配置；旧 schema 仅在内存迁移并提示，不修改用户文件。"""
        if not self.config_file.exists():
            return AppConfig()

        document, raw_bytes = self._read_document()
        plan = self._plan_document_migration(document, raw_bytes)
        if plan is not None:
            warnings.warn(
                f"Configuration schema {plan.source_version} is readable but "
                f"should be migrated to {plan.target_version}; run "
                "'autoblade config migrate' to preview it.",
                ConfigMigrationWarning,
                stacklevel=2,
            )
            migrated = tomlkit.parse(plan.migrated_text)
            return self._validate_document(migrated)
        return self._validate_document(document)

    def load_runtime(self) -> AppConfig:
        """返回路径均已解析为绝对路径的运行时配置副本。"""
        config = self.load().model_copy(deep=True)
        config_base_dir = self.config_file.parent

        # 1. 输入、输出根目录相对 config.toml 所在目录解析。
        input_dir = self._resolve_path(config.paths.input_dir, config_base_dir)
        output_dir = self._resolve_path(config.paths.output_dir, config_base_dir)

        # 2. 专用输入目录的相对值以 input_dir 为基准；绝对值保持不变。
        airfoil_dir = self._resolve_path(config.paths.airfoil_dir, input_dir)
        blade_sections_dir = self._resolve_path(
            config.paths.blade_sections_dir,
            input_dir,
        )

        config.paths.input_dir = input_dir
        config.paths.output_dir = output_dir
        config.paths.airfoil_dir = airfoil_dir
        config.paths.blade_sections_dir = blade_sections_dir
        return config

    @staticmethod
    def _resolve_path(path: str | Path, base_dir: Path) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (base_dir / candidate).resolve()

    @staticmethod
    def resolve_cli_path(path: str | Path) -> Path:
        """按命令行惯例，以当前工作目录解析用户显式传入的相对路径。"""
        return Path(path).expanduser().resolve()

    def save(self, config: AppConfig) -> None:
        """原子保存当前 schema；旧配置必须先显式迁移并生成备份。"""
        if self.config_file.exists():
            if self.plan_migration() is not None:
                raise ConfigMigrationRequiredError(
                    "Configuration requires an explicit schema or location "
                    "migration. Run "
                    "'autoblade config migrate' before changing it."
                )
        data = config.model_dump(mode="json")
        data["version"] = self.CURRENT_SCHEMA_VERSION
        self._atomic_write_text(tomlkit.dumps(data))

    def update_paths(self, **kwargs) -> None:
        config = self.load()
        for key, value in kwargs.items():
            if value is not None:
                setattr(config.paths, key, Path(value))
        self.save(config)

    def plan_migration(self) -> ConfigMigrationPlan | None:
        """返回真实 schema/用户目录迁移预览；无需迁移时返回 ``None``。"""
        if not self.config_file.is_file():
            raise FileNotFoundError(
                f"Configuration file does not exist: {self.config_file}"
            )
        document, raw_bytes = self._read_document()
        return self._plan_document_migration(
            document,
            raw_bytes,
            target_config_file=self._migration_target_file,
        )

    def apply_migration(self, plan: ConfigMigrationPlan) -> Path:
        """备份原文件并原子应用仍然有效的迁移计划。"""
        if plan.config_file != self.config_file:
            raise ConfigCompatibilityError(
                "Migration plan belongs to a different configuration file."
            )
        expected_target = self._migration_target_file or self.config_file
        if plan.target_config_file != expected_target:
            raise ConfigCompatibilityError(
                "Migration plan targets a different configuration location."
            )
        current_bytes = self.config_file.read_bytes()
        current_digest = hashlib.sha256(current_bytes).hexdigest()
        if current_digest != plan.original_sha256:
            raise ConfigCompatibilityError(
                "Configuration changed after the migration preview; preview it again."
            )

        target_file = plan.target_config_file
        moves_location = target_file != self.config_file
        if moves_location and target_file.exists():
            raise ConfigCompatibilityError(
                "Canonical configuration appeared after the migration preview: "
                f"{target_file}. Refusing to overwrite it."
            )

        backup = self._next_backup_path(plan.source_version)
        shutil.copy2(self.config_file, backup)
        try:
            self._atomic_write_text(plan.migrated_text, target_file=target_file)
            if moves_location:
                # 目标文件已经完整落盘且备份已存在，最后才移除旧活动文件。这样任一
                # 前置步骤失败时，旧目录仍是可读取的唯一配置来源。
                self.config_file.unlink()
        except Exception as error:
            # 跨目录无法依赖一次原子 rename；若旧文件移除失败，撤销刚创建的新文件，
            # 避免留下两份活动配置。备份始终保留，供人工恢复和审计。
            if moves_location and target_file.exists():
                try:
                    target_file.unlink()
                except OSError as cleanup_error:
                    error.add_note(
                        "Failed to remove the partially migrated canonical "
                        f"configuration: {cleanup_error}"
                    )
            raise

        if moves_location:
            self.config_file = target_file
            self.source = ConfigSource("user", target_file)
            self._migration_target_file = None
        return backup

    def _read_document(self) -> tuple[tomlkit.TOMLDocument, bytes]:
        raw_bytes = self.config_file.read_bytes()
        try:
            document = tomlkit.parse(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, tomlkit.exceptions.ParseError) as error:
            raise ConfigCompatibilityError(
                f"Invalid TOML configuration {self.config_file}: {error}"
            ) from error
        return document, raw_bytes

    def _plan_document_migration(
        self,
        document: tomlkit.TOMLDocument,
        raw_bytes: bytes,
        *,
        target_config_file: Path | None = None,
    ) -> ConfigMigrationPlan | None:
        source_version = str(document.get("version", "unversioned"))
        target_file = target_config_file or self.config_file
        moves_location = target_file != self.config_file
        if source_version == self.CURRENT_SCHEMA_VERSION:
            self._validate_document(document)
            if not moves_location:
                return None
            migrated = tomlkit.parse(tomlkit.dumps(document))
            changes: list[ConfigMigrationChange] = []
        else:
            if source_version not in self.LEGACY_SCHEMA_VERSIONS:
                self._raise_unsupported_version(source_version)

            migrated = tomlkit.parse(tomlkit.dumps(document))
            changes = []
            if source_version == "unversioned":
                changes.append(
                    ConfigMigrationChange(
                        "version",
                        "<missing>",
                        self.CURRENT_SCHEMA_VERSION,
                        "Record the configuration schema explicitly.",
                    )
                )
            else:
                changes.append(
                    ConfigMigrationChange(
                        "version",
                        source_version,
                        self.CURRENT_SCHEMA_VERSION,
                        "Upgrade to the current configuration schema.",
                    )
                )
            migrated["version"] = self.CURRENT_SCHEMA_VERSION

        # 1. schema 3.0.0 将用户可见集合统一命名为 blade_sections。旧默认
        #    目录同步改名；自定义目录值只改配置键，不猜测或移动用户数据。
        # 2. schema 1.0.0 曾把专用目录写成 input\\airfoils，同时运行时又以
        #    input_dir 为基准拼接。只剥离与 input_dir 完全相同的前缀，绝对路径、
        #    自定义同级路径以及用户的输出命名模板都保持原样。
        paths = migrated.get("paths")
        if source_version in {"unversioned", "1.0.0", "2.0.0"} and isinstance(
            paths,
            Mapping,
        ):
            input_dir = str(paths.get("input_dir", "input"))
            if "section_params_dir" in paths:
                if "blade_sections_dir" in paths:
                    raise ConfigCompatibilityError(
                        "Configuration contains both paths.section_params_dir "
                        "and paths.blade_sections_dir. Keep only one before "
                        "migration."
                    )
                before = str(paths.pop("section_params_dir"))
                after = self._strip_legacy_input_prefix(before, input_dir)
                after = self._rename_legacy_blade_sections_directory(after)
                paths["blade_sections_dir"] = after
                changes.append(
                    ConfigMigrationChange(
                        "paths.section_params_dir",
                        before,
                        after,
                        "Rename to paths.blade_sections_dir for schema 3.0.0.",
                    )
                )

            for field in ("airfoil_dir", "blade_sections_dir"):
                if field not in paths:
                    continue
                before = str(paths[field])
                after = self._strip_legacy_input_prefix(before, input_dir)
                if field == "blade_sections_dir":
                    after = self._rename_legacy_blade_sections_directory(after)
                if after != before:
                    paths[field] = after
                    changes.append(
                        ConfigMigrationChange(
                            f"paths.{field}",
                            before,
                            after,
                            "Keep the resolved directory stable under input_dir.",
                        )
                    )

        # schema v4 只补充后端默认值，不重复执行 v1/v2 的路径修正规则。
        # 保留已有用户配置和 TOML 注释；迁移仍受摘要、备份和原子替换保护。
        if source_version != self.CURRENT_SCHEMA_VERSION:
            for table_name, values in (
                ("defaults", {"backend": "catia"}),
                ("freecad", {"launcher": "flatpak", "app_id": "org.freecad.FreeCAD", "timeout_seconds": 900}),
            ):
                if table_name not in migrated:
                    migrated[table_name] = tomlkit.table()
                table = migrated[table_name]
                if isinstance(table, Mapping):
                    for key, value in values.items():
                        if key not in table:
                            table[key] = value
                            changes.append(ConfigMigrationChange(
                                f"{table_name}.{key}", "<missing>", str(value),
                                "Add explicit backend defaults for schema 4.0.0.",
                            ))

        if moves_location:
            self._preserve_location_relative_roots(
                migrated,
                target_file,
                changes,
            )
            changes.append(
                ConfigMigrationChange(
                    "config_file",
                    str(self.config_file),
                    str(target_file),
                    "Move the user configuration to the canonical AutoBlade directory.",
                )
            )

        self._validate_document(migrated)
        return ConfigMigrationPlan(
            config_file=self.config_file,
            target_config_file=target_file,
            source_version=source_version,
            target_version=self.CURRENT_SCHEMA_VERSION,
            changes=tuple(changes),
            original_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            migrated_text=tomlkit.dumps(migrated),
        )

    def _preserve_location_relative_roots(
        self,
        document: tomlkit.TOMLDocument,
        target_file: Path,
        changes: list[ConfigMigrationChange],
    ) -> None:
        """迁移配置文件位置时保持 input/output 的实际解析目录不变。

        用户级配置中的 ``input_dir`` 和 ``output_dir`` 以配置文件目录为基准。只把
        TOML 移到新产品目录会悄悄切换输入和输出位置，因此迁移计划会把相对根路径
        改写为相对于新目录、但仍指向旧实际目录的值。专用输入子目录继续相对于
        ``input_dir`` 解析，无需重复改写。
        """
        paths = document.get("paths")
        if not isinstance(paths, Mapping):
            paths = tomlkit.table()
            document["paths"] = paths

        for field, default in (
            ("input_dir", "input"),
            ("output_dir", "output"),
        ):
            before = str(paths.get(field, default))
            candidate = Path(before).expanduser()
            if candidate.is_absolute():
                continue
            resolved_before = (self.config_file.parent / candidate).resolve()
            try:
                after = os.path.relpath(resolved_before, target_file.parent)
            except ValueError:
                # Windows 不同盘符间不存在相对路径；使用绝对路径仍能保持解析结果。
                after = str(resolved_before)
            if after == before and field in paths:
                continue
            paths[field] = after
            changes.append(
                ConfigMigrationChange(
                    f"paths.{field}",
                    before,
                    after,
                    "Preserve the resolved directory after moving config.toml.",
                )
            )

    def _validate_document(self, document: Mapping[str, Any]) -> AppConfig:
        deprecated = [
            (field, replacement)
            for field, replacement in self.DEPRECATED_FIELDS.items()
            if self._contains_dotted_field(document, field)
        ]
        if deprecated:
            details = ", ".join(
                f"{field} (use {replacement})"
                for field, replacement in deprecated
            )
            raise ConfigCompatibilityError(
                f"Deprecated configuration field(s): {details}."
            )

        try:
            config = AppConfig.model_validate(document)
        except ValidationError as error:
            unknown_fields = [
                ".".join(str(part) for part in item["loc"])
                for item in error.errors()
                if item["type"] == "extra_forbidden"
            ]
            if unknown_fields:
                raise ConfigCompatibilityError(
                    "Unknown configuration field(s): "
                    f"{', '.join(sorted(unknown_fields))}. Refusing to ignore "
                    "them because a later save could lose user settings."
                ) from error
            raise ConfigCompatibilityError(
                f"Invalid configuration {self.config_file}: {error}"
            ) from error

        if config.version != self.CURRENT_SCHEMA_VERSION:
            raise ConfigCompatibilityError(
                f"Configuration validation produced unexpected schema "
                f"{config.version!r}."
            )
        return config

    def _raise_unsupported_version(self, source_version: str) -> None:
        current = self._parse_version(self.CURRENT_SCHEMA_VERSION)
        candidate = self._parse_version(source_version)
        if candidate is not None and current is not None and candidate > current:
            raise ConfigCompatibilityError(
                f"Configuration schema {source_version} is newer than supported "
                f"schema {self.CURRENT_SCHEMA_VERSION}; upgrade AutoBlade."
            )
        raise ConfigCompatibilityError(
            f"Unsupported configuration schema {source_version!r}; supported "
            f"legacy schemas: {sorted(self.LEGACY_SCHEMA_VERSIONS)}."
        )

    @staticmethod
    def _parse_version(value: str) -> tuple[int, int, int] | None:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
        if match is None:
            return None
        return tuple(int(part) for part in match.groups())

    @staticmethod
    def _strip_legacy_input_prefix(value: str, input_dir: str) -> str:
        candidate = value.replace("\\", "/")
        base = input_dir.replace("\\", "/")
        if Path(value).is_absolute() or Path(input_dir).is_absolute():
            return value
        candidate_parts = [part for part in candidate.split("/") if part not in ("", ".")]
        base_parts = [part for part in base.split("/") if part not in ("", ".")]
        if not base_parts or candidate_parts[: len(base_parts)] != base_parts:
            return value
        remaining = candidate_parts[len(base_parts) :]
        return str(Path(*remaining)) if remaining else value

    @staticmethod
    def _rename_legacy_blade_sections_directory(value: str) -> str:
        """只迁移旧默认目录名，保留所有自定义或绝对路径。"""
        normalized = value.replace("\\", "/").removeprefix("./")
        if normalized == "section_params":
            return "blade_sections"
        return value

    @staticmethod
    def _contains_dotted_field(document: Mapping[str, Any], field: str) -> bool:
        current: Any = document
        for part in field.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return False
            current = current[part]
        return True

    def _next_backup_path(self, source_version: str) -> Path:
        safe_version = re.sub(r"[^0-9A-Za-z.-]+", "-", source_version)
        base = self.config_file.with_name(
            f"{self.config_file.name}.v{safe_version}.bak"
        )
        if not base.exists():
            return base
        index = 1
        while True:
            candidate = base.with_name(f"{base.name}.{index}")
            if not candidate.exists():
                return candidate
            index += 1

    def _atomic_write_text(
        self,
        content: str,
        *,
        target_file: Path | None = None,
    ) -> None:
        destination = target_file or self.config_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.{uuid4().hex}.tmp"
        )
        try:
            temporary.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
