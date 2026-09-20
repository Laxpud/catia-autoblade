"""CLI/config 在 Planner 前确定后端，交互入口也复用相同优先级。"""

from pathlib import Path
import math

from ..config.settings import AppConfig
from ..core.backend import BackendName, BackendOptions


def resolve_backend_options(
    config: AppConfig,
    *,
    backend: BackendName | str | None = None,
    timeout_seconds: float | None = None,
    dependency_override: Path | None = None,
    verbose: bool = False,
    keep_failed_part: bool = False,
) -> BackendOptions:
    """只做纯配置解析，dry-run 不查找 launcher 或加载依赖。"""
    selected = BackendName(backend or config.defaults.backend)
    timeout = (
        config.freecad.timeout_seconds if timeout_seconds is None else timeout_seconds
    )
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("--timeout-seconds must be a finite positive number.")
    if selected == BackendName.CATIA and (
        timeout_seconds is not None or dependency_override is not None
    ):
        raise ValueError(
            "--timeout-seconds and --freecad-dependency-dir require the FreeCAD backend."
        )
    return dict(
        backend=selected,
        timeout_seconds=timeout,
        freecad_app_id=config.freecad.app_id,
        dependency_override=dependency_override.resolve()
        if dependency_override
        else None,
        verbose=verbose,
        keep_failed_part=keep_failed_part,
    )
