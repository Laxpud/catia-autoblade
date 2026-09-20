from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import os
from pathlib import Path
import platform
import sys
import tempfile
from typing import Callable

import typer

from .. import __version__
from ..config.manager import ConfigManager
from ..core.backend import BackendName


SUPPORTED_PYTHON = (3, 14)
SUPPORTED_PYWIN32 = "311"
SUPPORTED_CATIA = "CATIA P3 V5-6R2020 (manual confirmation required)"


@dataclass(frozen=True)
class DoctorCheck:
    """一项无破坏性环境诊断及其可复制结果。"""

    name: str
    status: str
    detail: str


class DoctorFailure(RuntimeError):
    """至少一个安装前置条件明确失败。"""


def run_doctor_command(
    *,
    config_manager: ConfigManager | None = None,
    backend: BackendName | None = None,
    all_backends: bool = False,
    collector: Callable[[ConfigManager], list[DoctorCheck]] | None = None,
) -> list[DoctorCheck]:
    """输出不连接 CATIA 的诊断摘要，并让明确失败反映到退出码。"""
    manager = config_manager or ConfigManager()
    if collector is not None:
        checks = collector(manager)
    else:
        selected = backend or manager.load_runtime().defaults.backend
        checks = []
        if all_backends or selected == BackendName.CATIA:
            checks.extend(collect_doctor_checks(manager))
        if all_backends or selected == BackendName.FREECAD:
            checks.extend(collect_freecad_checks(manager))
    typer.echo("AutoBlade doctor")
    typer.echo(f"app_version: {__version__}")
    for check in checks:
        typer.echo(f"{check.name}: {check.status} - {check.detail}")
    overall = "FAIL" if any(check.status == "FAIL" for check in checks) else "PASS"
    if overall == "PASS" and any(check.status == "WARN" for check in checks):
        overall = "WARN"
    typer.echo(f"overall: {overall}")
    if overall == "FAIL":
        raise DoctorFailure("Environment diagnostics reported failures.")
    return checks


def collect_doctor_checks(manager: ConfigManager) -> list[DoctorCheck]:
    """收集静态注册和写权限证据；绝不 Dispatch/DispatchEx CATIA。"""
    checks = [_check_platform(), _check_python(), _check_pywin32()]
    checks.append(_check_com_initialization())
    checks.append(_check_catia_registration())

    try:
        config = manager.load_runtime()
        plan = manager.plan_migration() if manager.config_file.is_file() else None
        if plan is None:
            config_detail = manager.source_description
            config_status = "PASS"
        else:
            migrations = []
            if plan.source_version != plan.target_version:
                migrations.append(
                    f"schema {plan.source_version} -> {plan.target_version}"
                )
            if plan.config_file != plan.target_config_file:
                migrations.append(
                    f"location {plan.config_file} -> {plan.target_config_file}"
                )
            config_detail = (
                f"{manager.source_description}; "
                f"{', '.join(migrations)} migration available"
            )
            config_status = "WARN"
        checks.append(DoctorCheck("config", config_status, config_detail))
        checks.append(_check_directory("airfoil_dir", config.paths.airfoil_dir))
        checks.append(
            _check_directory(
                "blade_sections_dir",
                config.paths.blade_sections_dir,
            )
        )
        checks.append(_check_output_writable(config.paths.output_dir))
    except Exception as error:
        checks.append(DoctorCheck("config", "FAIL", str(error)))

    baseline_inputs = {check.name: check for check in checks}
    platform_ok = baseline_inputs["windows"].status == "PASS"
    python_ok = baseline_inputs["python"].status == "PASS"
    pywin32_ok = baseline_inputs["pywin32"].status == "PASS"
    if platform_ok and python_ok and pywin32_ok:
        detail = (
            "Windows/Python/pywin32 match the recorded preview baseline; "
            f"verify {SUPPORTED_CATIA}."
        )
        checks.append(DoctorCheck("support_baseline", "WARN", detail))
    else:
        checks.append(
            DoctorCheck(
                "support_baseline",
                "FAIL",
                "Windows 11 x64, CPython 3.14.x x64, and pywin32 311 are required.",
            )
        )
    return checks


def _check_platform() -> DoctorCheck:
    system = platform.system()
    machine = platform.machine()
    is_windows_x64 = system == "Windows" and machine.upper() in {
        "AMD64",
        "X86_64",
    }
    status = "PASS" if is_windows_x64 else "FAIL"
    return DoctorCheck("windows", status, f"{system} {platform.release()} {machine}")


def _check_python() -> DoctorCheck:
    current = (sys.version_info.major, sys.version_info.minor)
    architecture = platform.architecture()[0]
    supported = current == SUPPORTED_PYTHON and architecture == "64bit"
    return DoctorCheck(
        "python",
        "PASS" if supported else "FAIL",
        f"{platform.python_version()} {architecture} ({sys.executable})",
    )


def _check_pywin32() -> DoctorCheck:
    try:
        version = metadata.version("pywin32")
    except metadata.PackageNotFoundError:
        return DoctorCheck("pywin32", "FAIL", "not installed")
    status = "PASS" if version == SUPPORTED_PYWIN32 else "FAIL"
    return DoctorCheck("pywin32", status, version)


def _check_com_initialization() -> DoctorCheck:
    try:
        import pythoncom
    except ImportError as error:
        return DoctorCheck("com_initialization", "FAIL", str(error))

    initialized = False
    try:
        pythoncom.CoInitialize()
        initialized = True
        return DoctorCheck("com_initialization", "PASS", "CoInitialize succeeded")
    except Exception as error:
        return DoctorCheck("com_initialization", "FAIL", str(error))
    finally:
        if initialized:
            pythoncom.CoUninitialize()


def _check_catia_registration() -> DoctorCheck:
    if os.name != "nt":
        return DoctorCheck("catia_registration", "FAIL", "Windows registry unavailable")
    try:
        import winreg

        # 仅读取 ProgID 注册；不调用 Dispatch，因此不会连接、启动或退出任何
        # 用户 CATIA 会话，也不会消耗许可证。
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            r"CATIA.Application\CLSID",
        ) as key:
            clsid, _ = winreg.QueryValueEx(key, None)
    except OSError as error:
        return DoctorCheck("catia_registration", "FAIL", str(error))
    return DoctorCheck("catia_registration", "PASS", f"CLSID {clsid}")


def _check_directory(name: str, path: Path) -> DoctorCheck:
    if not path.is_dir():
        return DoctorCheck(name, "FAIL", f"missing directory: {path}")
    return DoctorCheck(name, "PASS", str(path))


def _check_output_writable(path: Path) -> DoctorCheck:
    """用临时探针验证真实写权限；输出目录不存在时检查最近已有父目录。"""
    ancestor = path
    while not ancestor.exists():
        if ancestor.parent == ancestor:
            return DoctorCheck("output_writable", "FAIL", f"no parent for {path}")
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        return DoctorCheck(
            "output_writable",
            "FAIL",
            f"output parent is not a directory: {ancestor}",
        )
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".autoblade-doctor-",
            dir=ancestor,
            delete=True,
        ):
            pass
    except OSError as error:
        return DoctorCheck("output_writable", "FAIL", f"{path}: {error}")
    detail = str(path) if path.exists() else f"creatable under {ancestor}"
    return DoctorCheck("output_writable", "PASS", detail)


def collect_freecad_checks(manager: ConfigManager) -> list[DoctorCheck]:
    """所选 FreeCAD 后端运行短探针；失败不能被另一后端的 PASS 抵消。"""
    from ..adapters.cad.freecad.adapter import probe_backend

    checks = [_check_python()]
    try:
        config = manager.load_runtime()
        checks.extend([
            DoctorCheck("config", "PASS", manager.source_description),
            _check_directory("airfoil_dir", config.paths.airfoil_dir),
            _check_directory("blade_sections_dir", config.paths.blade_sections_dir),
            _check_output_writable(config.paths.output_dir),
        ])
        detail = probe_backend(config.paths.output_dir, app_id=config.freecad.app_id,
                               timeout=config.freecad.timeout_seconds)
        status = "PASS" if detail.startswith("FreeCAD 1.1.3;") else "WARN"
        checks.append(DoctorCheck("freecad", status, detail))
    except Exception as error:
        checks.append(DoctorCheck("freecad", "FAIL", str(error)))
    return checks
