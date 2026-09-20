from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from autoblade.commands import doctor
from autoblade.config.manager import ConfigManager


def test_doctor_summary_is_copyable_and_warn_does_not_fail(capsys) -> None:
    checks = [
        doctor.DoctorCheck("windows", "PASS", "Windows 11 AMD64"),
        doctor.DoctorCheck("support_baseline", "WARN", "confirm CATIA manually"),
    ]

    result = doctor.run_doctor_command(
        config_manager=ConfigManager(Path("missing.toml")),
        collector=lambda manager: checks,
    )

    assert result == checks
    output = capsys.readouterr().out
    assert "windows: PASS - Windows 11 AMD64" in output
    assert "overall: WARN" in output


def test_doctor_failure_is_visible_after_complete_summary(capsys) -> None:
    checks = [doctor.DoctorCheck("catia_registration", "FAIL", "not registered")]

    with pytest.raises(doctor.DoctorFailure):
        doctor.run_doctor_command(
            config_manager=ConfigManager(Path("missing.toml")),
            collector=lambda manager: checks,
        )

    output = capsys.readouterr().out
    assert "catia_registration: FAIL" in output
    assert "overall: FAIL" in output


def test_com_initialization_probe_balances_initialize_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    fake_pythoncom = SimpleNamespace(
        CoInitialize=lambda: calls.append("initialize"),
        CoUninitialize=lambda: calls.append("uninitialize"),
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)

    result = doctor._check_com_initialization()

    assert result.status == "PASS"
    assert calls == ["initialize", "uninitialize"]


def test_doctor_checks_configured_directories_without_starting_catia(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    (input_dir / "airfoils").mkdir(parents=True)
    (input_dir / "sections").mkdir()
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """version = "4.0.0"
[paths]
input_dir = "input"
output_dir = "output"
airfoil_dir = "airfoils"
blade_sections_dir = "sections"
[defaults]
author = ""
output_name_template = "{blade}"
""",
        encoding="utf-8",
    )
    def passed(name: str) -> doctor.DoctorCheck:
        return doctor.DoctorCheck(name, "PASS", "test")

    monkeypatch.setattr(doctor, "_check_platform", lambda: passed("windows"))
    monkeypatch.setattr(doctor, "_check_python", lambda: passed("python"))
    monkeypatch.setattr(doctor, "_check_pywin32", lambda: passed("pywin32"))
    monkeypatch.setattr(
        doctor,
        "_check_com_initialization",
        lambda: passed("com_initialization"),
    )
    monkeypatch.setattr(
        doctor,
        "_check_catia_registration",
        lambda: passed("catia_registration"),
    )

    checks = doctor.collect_doctor_checks(ConfigManager(config_file))

    by_name = {check.name: check for check in checks}
    assert by_name["config"].status == "PASS"
    assert by_name["airfoil_dir"].status == "PASS"
    assert by_name["blade_sections_dir"].status == "PASS"
    assert by_name["output_writable"].status == "PASS"
    assert by_name["support_baseline"].status == "WARN"
