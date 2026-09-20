"""阶段 3 的 Host 契约；所有进程均为 fake，不需要真实 CAD。"""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import zipfile

import pytest
from typer.testing import CliRunner

from autoblade.cli import app
from autoblade.config.manager import ConfigManager, ConfigMigrationWarning
from autoblade.config.settings import AppConfig
from autoblade.core.backend import BackendName, BackendError
from autoblade.core.executor import execute_jobs
from autoblade.core.planner import plan_create_job
from autoblade.adapters.cad import factory
from autoblade.adapters.cad.freecad import adapter, artifacts, process, protocol

ROOT = Path(__file__).resolve().parents[1]


def make_job(tmp_path, **kwargs):
    return plan_create_job(
        "naca0012_sharp.csv",
        "blade_sections-naca.csv",
        tmp_path,
        airfoil_dir=ROOT / "input/airfoils",
        blade_sections_dir=ROOT / "input/blade_sections",
        output_name_template="{blade}",
        author="",
        backend=BackendName.FREECAD,
        **kwargs,
    )


def write_fcstd(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", "<Document/>")


def completed_process(command, *, env, timeout):
    """模拟 Child 的独立写入和重开证据，Host 仍需自行验证实际文件。"""
    staging = Path(env["AUTOBLADE_FREECAD_OUTPUT_DIR"])
    request = json.loads((staging / "request.json").read_text())
    digests = protocol.validate_curveswb_checkout(
        Path(env["AUTOBLADE_FREECAD_CURVESWB_DIR"]),
        custom=env["AUTOBLADE_FREECAD_CUSTOM"] == "1",
    )
    native = staging / request["artifacts"]["native_model"]
    step = staging / request["artifacts"]["step"]
    write_fcstd(native)
    step.write_text(
        "ISO-10303-21; FILE_SCHEMA(('AP242')); SI_UNIT(.MILLI.,.METRE.); UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-7),#1,'',''); END-ISO-10303-21;"
    )
    digest = protocol.request_sha256(request)
    result = {
        "schema_version": protocol.RESULT_SCHEMA,
        "status": "passed",
        "freecad_version": ["1", "1", "3"],
        "curveswb_commit": protocol.CURVESWB_COMMIT,
        "curveswb_version": protocol.CURVESWB_VERSION,
        "dependency_status": "unverified_custom_dependency"
        if env["AUTOBLADE_FREECAD_CUSTOM"] == "1"
        else "pinned",
        "dependency_fingerprint_sha256": hashlib.sha256(
            protocol.canonical_json(digests).encode()
        ).hexdigest(),
        "request_sha256": digest,
        "request_source": "closed_json",
        "elapsed_seconds": 1.0,
        "peak_rss_kib": 100,
        "measurements": {
            "reopen": {
                "fcstd_valid": True,
                "fcstd_closed": True,
                "fcstd_solids": 1,
                "step_valid": True,
                "step_solids": 1,
                "embedded_request_sha256": digest,
            }
        },
        "artifacts": {
            "native_model": str(native),
            "step": str(step),
            "native_model_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
            "step_sha256": hashlib.sha256(step.read_bytes()).hexdigest(),
        },
    }
    (staging / "result.json").write_text(json.dumps(result))
    return 0, "fake stdout", "fake stderr"


@pytest.fixture
def fake_backend(monkeypatch):
    monkeypatch.setattr(adapter, "build_command", lambda **kwargs: ["fake-freecad"])
    monkeypatch.setattr(adapter, "run_process", completed_process)


def test_backend_plans_real_artifact_types_and_preserves_default(tmp_path):
    freecad = make_job(tmp_path)
    catia = replace(freecad, backend=BackendName.CATIA)
    assert [a.format for a in freecad.artifacts] == ["FCStd", "STEP"]
    assert [a.path.suffix for a in catia.artifacts] == [".CATPart", ".stp"]
    assert AppConfig().defaults.backend == BackendName.CATIA
    with pytest.raises(ValueError):
        factory.get_backend("unknown")


def test_v3_migration_preserves_paths_comments_and_backup(tmp_path):
    path = tmp_path / "config.toml"
    original = '# Keep this comment\nversion = "3.0.0"\n[paths]\ninput_dir = "input"\nairfoil_dir = "input/custom"\n'
    path.write_text(original)
    manager = ConfigManager(path)
    plan = manager.plan_migration()
    assert plan.source_version == "3.0.0" and plan.target_version == "4.0.0"
    with pytest.warns(ConfigMigrationWarning):
        config = manager.load_runtime()
    assert path.read_text() == original
    assert config.paths.airfoil_dir == tmp_path / "input/input/custom"
    assert config.defaults.backend == "catia" and config.freecad.timeout_seconds == 900
    backup = manager.apply_migration(plan)
    assert backup.read_text() == original
    assert "# Keep this comment" in path.read_text()
    assert manager.plan_migration() is None


@pytest.mark.parametrize("command", ["create", "batch", "sweep"])
@pytest.mark.parametrize("backend", ["catia", "freecad"])
def test_all_commands_dry_run_and_backend_override_without_cad(
    tmp_path, monkeypatch, command, backend
):
    config = AppConfig()
    config.paths.input_dir = ROOT / "input"
    config.paths.output_dir = tmp_path / "output"
    config.defaults.backend = BackendName.FREECAD
    manager = ConfigManager(tmp_path / "config.toml")
    manager.save(config)
    selected = make_job(config.paths.output_dir)
    if backend == "freecad":
        target = selected.output_paths[1]
        if command != "create":
            target = target.parent / "naca0012_sharp" / target.name
        target.parent.mkdir(parents=True)
        target.write_text("old STEP only")
    monkeypatch.setattr(
        factory, "get_backend", lambda name: pytest.fail("dry-run started CAD")
    )
    result = CliRunner().invoke(
        app,
        [
            "--config",
            str(manager.config_file),
            command,
            "--backend",
            backend,
            "-a",
            "naca0012_sharp.csv",
            "-s",
            "blade_sections-naca.csv",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (".FCStd" if backend == "freecad" else ".CATPart") in result.output
    assert "CAD was not started" in result.output
    if backend == "freecad":
        assert "overwrite=" in result.output
    if command == "sweep":
        assert (
            '"schema_version": 3' in result.output
            and '"output_files"' not in result.output
        )
        assert f'"backend": "{backend}"' in result.output


def test_freecad_success_publishes_complete_pair_and_removes_staging(
    tmp_path, fake_backend
):
    job = make_job(tmp_path)
    for path in job.output_paths:
        path.write_text("old artifact")
    adapter.FreeCADBackend().build(job)
    assert artifacts.recognizable_fcstd(job.output_paths[0])
    assert "AP242" in job.output_paths[1].read_text()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        p.name for p in job.output_paths
    )


@pytest.mark.parametrize(
    "defect",
    [
        "absent",
        "json",
        "schema",
        "unknown",
        "request",
        "dependency",
        "artifacts",
        "reopen",
        "missing_native",
        "empty_step",
        "exit",
    ],
)
def test_zero_exit_and_incomplete_protocol_or_artifacts_never_succeed(
    tmp_path, fake_backend, monkeypatch, defect
):
    job = make_job(tmp_path)
    for path in job.output_paths:
        path.write_text("previous")

    def broken(command, *, env, timeout):
        completed_process(command, env=env, timeout=timeout)
        staging = Path(env["AUTOBLADE_FREECAD_OUTPUT_DIR"])
        path = staging / "result.json"
        value = json.loads(path.read_text())
        if defect == "absent":
            path.unlink()
        elif defect == "json":
            path.write_text("{")
        elif defect == "missing_native":
            (staging / job.output_paths[0].name).unlink()
        elif defect == "empty_step":
            (staging / job.output_paths[1].name).write_text("")
        else:
            if defect == "schema":
                value["schema_version"] = "future"
            if defect == "unknown":
                value["unknown"] = 1
            if defect == "request":
                value["request_sha256"] = "0" * 64
            if defect == "dependency":
                value["dependency_fingerprint_sha256"] = "0" * 64
            if defect == "artifacts":
                del value["artifacts"]
            if defect == "reopen":
                value["measurements"]["reopen"]["step_valid"] = False
            path.write_text(json.dumps(value))
        return (1 if defect == "exit" else 0), "out", "err"

    monkeypatch.setattr(adapter, "run_process", broken)
    with pytest.raises(BackendError) as error:
        adapter.FreeCADBackend().build(job)
    assert error.value.code in {"protocol", "artifact_validation"}
    assert [p.read_text() for p in job.output_paths] == ["previous", "previous"]
    assert not list(tmp_path.glob(".autoblade-*"))


@pytest.mark.parametrize("old_count", [0, 1, 2])
def test_partial_publication_rolls_back_exact_old_set(tmp_path, monkeypatch, old_count):
    staging = tmp_path / ".autoblade-test"
    staging.mkdir()
    targets = (tmp_path / "blade.FCStd", tmp_path / "blade.stp")
    for target in targets[:old_count]:
        target.write_text("old")
    for target in targets:
        (staging / target.name).write_text("new")
    original = artifacts.os.replace

    def fail_second(source, target):
        if source == staging / "blade.stp":
            raise OSError("injected publication failure")
        original(source, target)

    monkeypatch.setattr(artifacts.os, "replace", fail_second)
    with pytest.raises(BackendError, match="rolled back"):
        artifacts.publish(staging, targets)
    assert [p.read_text() for p in targets[:old_count]] == ["old"] * old_count
    assert not any(p.exists() for p in targets[old_count:])


def test_timeout_snapshot_is_optional_and_does_not_overwrite(
    tmp_path, fake_backend, monkeypatch
):
    job = make_job(tmp_path, keep_failed_part=True)
    old = tmp_path / f"{job.output_name}_failed.FCStd"
    old.write_text("old")

    def timeout(command, *, env, timeout):
        write_fcstd(
            Path(env["AUTOBLADE_FREECAD_OUTPUT_DIR"]) / job.output_paths[0].name
        )
        raise BackendError(BackendName.FREECAD, "timeout", "Timeout")

    monkeypatch.setattr(adapter, "run_process", timeout)
    with pytest.warns(UserWarning, match="Failed model saved"):
        with pytest.raises(BackendError) as error:
            adapter.FreeCADBackend().build(job)
    assert error.value.code == "timeout"
    assert old.read_text() == "old"
    assert len(list(tmp_path.glob("*_failed_*.FCStd"))) == 1
    assert not job.output_paths[1].exists()
    assert not list(tmp_path.glob(".autoblade-*"))


def test_batch_failure_continues_but_interrupt_stops(tmp_path, monkeypatch):
    jobs = [make_job(tmp_path / str(i)) for i in range(3)]
    calls = []

    def build(job):
        calls.append(job)
        if len(calls) == 1:
            raise BackendError(BackendName.FREECAD, "geometry", "bad geometry")

    monkeypatch.setattr(
        factory, "get_backend", lambda name: SimpleNamespace(build=build)
    )
    results = execute_jobs(jobs)
    assert [r.status for r in results] == ["failed", "success", "success"]
    assert results[0].error_code == "geometry"
    calls.clear()

    def interrupt(job):
        calls.append(job)
        raise KeyboardInterrupt

    monkeypatch.setattr(
        factory, "get_backend", lambda name: SimpleNamespace(build=interrupt)
    )
    with pytest.raises(KeyboardInterrupt):
        execute_jobs(jobs)
    assert calls == jobs[:1]


@pytest.mark.parametrize("interrupt", [False, True])
def test_process_timeout_or_interrupt_cleans_only_owned_group(monkeypatch, interrupt):
    calls = []
    fake = SimpleNamespace(pid=98765, returncode=0)
    responses = iter(
        [
            KeyboardInterrupt() if interrupt else subprocess.TimeoutExpired("fake", 1),
            ("out", "err"),
        ]
    )

    def communicate(timeout):
        response = next(responses)
        if isinstance(response, BaseException):
            raise response
        return response

    fake.communicate = communicate
    monkeypatch.setattr(process.subprocess, "Popen", lambda *a, **kw: fake)
    monkeypatch.setattr(
        process.os, "killpg", lambda pid, sig: calls.append((pid, sig)), raising=False
    )
    with pytest.raises(KeyboardInterrupt if interrupt else BackendError):
        process.run_process(["fake"], env={}, timeout=1)
    assert len(calls) == 1 and calls[0][0] == 98765


def test_vendor_integrity_and_explicit_override(tmp_path):
    vendor = adapter.bundled_dependency()
    digests = protocol.validate_curveswb_checkout(vendor)
    assert len(digests) == 7
    custom = tmp_path / "custom"
    shutil.copytree(vendor, custom)
    path = custom / "freecad/Curves/gordon.py"
    path.write_bytes(path.read_bytes() + b"\n# Custom test modification\n")
    with pytest.raises(protocol.ProtocolError, match="fingerprint mismatch"):
        protocol.validate_curveswb_checkout(custom)
    actual = protocol.validate_curveswb_checkout(custom, custom=True)
    assert actual != digests


def test_no_interior_knots_is_not_a_continuity_failure():
    # Runner 只在 CAD 解释器中导入；抽取纯函数测试数学判定，不能导入触发 run()。
    import ast

    path = ROOT / "src/autoblade/adapters/cad/freecad/runner.py"
    function = next(
        node
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "_continuity"
    )
    namespace = {"Any": object}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    surface = SimpleNamespace(
        VDegree=1, getVMultiplicities=lambda: [2, 2], getVKnots=lambda: [0, 1]
    )
    assert (
        namespace["_continuity"](surface, "v")["minimum_interior_continuity_order"]
        is None
    )
    surface.VDegree = 3
    surface.getVMultiplicities = lambda: [4, 2, 4]
    surface.getVKnots = lambda: [0, 0.5, 1]
    assert (
        namespace["_continuity"](surface, "v")["minimum_interior_continuity_order"] == 1
    )


@pytest.mark.parametrize("command", ["create", "batch", "sweep"])
@pytest.mark.parametrize("interactive", [False, True])
def test_commands_execute_selected_backend_and_confirm_real_paths(
    tmp_path, monkeypatch, command, interactive
):
    from autoblade.interactive import prompts

    config = AppConfig()
    config.paths.input_dir = ROOT / "input"
    config.paths.output_dir = tmp_path / "output"
    config.defaults.backend = BackendName.FREECAD
    manager = ConfigManager(tmp_path / "config.toml")
    manager.save(config)
    calls, confirms = [], []
    monkeypatch.setattr(
        factory, "get_backend", lambda name: SimpleNamespace(build=calls.append)
    )
    monkeypatch.setattr(prompts, "confirm_output_dir", lambda default: default)
    monkeypatch.setattr(prompts, "confirm_execution", lambda: confirms.append(True))
    args = [
        "--config",
        str(manager.config_file),
        command,
        "-a",
        "naca0012_sharp.csv",
        "-s",
        "blade_sections-naca.csv",
    ]
    if interactive:
        args.append("--interactive")
    result = CliRunner().invoke(
        app, args + ["--keep-failed-model", "--timeout-seconds", "12"]
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0].backend == BackendName.FREECAD and calls[0].keep_failed_part
    assert calls[0].timeout_seconds == 12
    assert len(confirms) == int(interactive)
    assert ".FCStd" in result.output and ".CATPart" not in result.output


@pytest.mark.parametrize("command", ["batch", "sweep"])
@pytest.mark.parametrize("interrupt", [False, True])
def test_bulk_cli_failure_continues_and_interrupt_stops(
    tmp_path, monkeypatch, command, interrupt
):
    config = AppConfig()
    config.paths.input_dir = ROOT / "input"
    config.paths.output_dir = tmp_path / "output"
    manager = ConfigManager(tmp_path / "config.toml")
    manager.save(config)
    calls = []

    def build(job):
        calls.append(job)
        if len(calls) == 1:
            if interrupt:
                raise KeyboardInterrupt
            raise BackendError(BackendName.FREECAD, "geometry", "injected failure")

    monkeypatch.setattr(
        factory, "get_backend", lambda name: SimpleNamespace(build=build)
    )
    args = [
        "--config",
        str(manager.config_file),
        command,
        "--backend",
        "freecad",
        "-a",
        "naca0012_sharp.csv",
    ]
    if command == "sweep":
        args += ["-a", "sc1095.csv", "-s", "blade_sections-naca.csv"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == (130 if interrupt else 1), result.output
    assert (len(calls) == 1) if interrupt else (len(calls) > 1)


def test_doctor_selects_only_requested_backend_and_all_fails(tmp_path, monkeypatch):
    from autoblade.commands import doctor

    manager = ConfigManager(tmp_path / "config.toml")
    manager.save(AppConfig())
    calls = []

    def collect(name, status):
        def action(manager):
            calls.append(name)
            return [doctor.DoctorCheck(name, status, "fake")]

        return action

    monkeypatch.setattr(doctor, "collect_doctor_checks", collect("catia", "FAIL"))
    monkeypatch.setattr(doctor, "collect_freecad_checks", collect("freecad", "PASS"))
    doctor.run_doctor_command(config_manager=manager, backend=BackendName.FREECAD)
    assert calls == ["freecad"]
    calls.clear()
    with pytest.raises(doctor.DoctorFailure):
        doctor.run_doctor_command(config_manager=manager, all_backends=True)
    assert calls == ["catia", "freecad"]


def test_mixed_backends_rejected_before_factory(tmp_path, monkeypatch):
    job = make_job(tmp_path)
    monkeypatch.setattr(
        factory, "get_backend", lambda name: pytest.fail("mixed jobs executed")
    )
    with pytest.raises(ValueError, match="mix CAD backends"):
        execute_jobs([job, replace(job, backend=BackendName.CATIA)])


def test_dependency_override_is_recorded_by_child_contract(
    tmp_path, monkeypatch, fake_backend
):
    custom = tmp_path / "custom"
    shutil.copytree(adapter.bundled_dependency(), custom)
    job = make_job(tmp_path / "output", dependency_override=custom)
    with pytest.warns(UserWarning, match="unverified_custom_dependency"):
        adapter.FreeCADBackend().build(job)
    assert all(path.exists() for path in job.output_paths)


def test_cleanup_failure_preserves_rollback_evidence(
    tmp_path, monkeypatch, fake_backend
):
    job = make_job(tmp_path)
    for path in job.output_paths:
        path.write_text("old")
    original = artifacts.os.replace

    def fail_publication_and_restore(source, target):
        if Path(source).name in {job.output_paths[1].name, "previous-0"}:
            raise OSError("injected rollback failure")
        original(source, target)

    monkeypatch.setattr(artifacts.os, "replace", fail_publication_and_restore)
    with pytest.raises(BackendError) as error:
        adapter.FreeCADBackend().build(job)
    assert error.value.code == "cleanup"
    staging = next(tmp_path.glob(".autoblade-*"))
    assert (staging / "previous-0").read_text() == "old"


def test_child_environment_discards_stale_request_and_python_path(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AUTOBLADE_FREECAD_REBUILD_FCSTD", "/stale.FCStd")
    monkeypatch.setenv("AUTOBLADE_FREECAD_CUSTOM", "1")
    monkeypatch.setenv("PYTHONPATH", "/stale-python")
    env = process.child_environment(tmp_path, tmp_path / "dependency")
    assert "AUTOBLADE_FREECAD_REBUILD_FCSTD" not in env
    assert "AUTOBLADE_FREECAD_CUSTOM" not in env
    assert "PYTHONPATH" not in env
    assert env["PYTHONNOUSERSITE"] == "1"


def test_failed_result_retains_complete_stdout_stderr(
    tmp_path, fake_backend, monkeypatch
):
    def fail(command, *, env, timeout):
        completed_process(command, env=env, timeout=timeout)
        result_path = Path(env["AUTOBLADE_FREECAD_OUTPUT_DIR"]) / "result.json"
        value = json.loads(result_path.read_text())
        value.update(
            status="failed",
            error_code="geometry",
            error="Traceback\nValueError: bad solid",
        )
        result_path.write_text(json.dumps(value))
        return 0, "child stdout", "child stderr"

    monkeypatch.setattr(adapter, "run_process", fail)
    with pytest.raises(BackendError, match="bad solid") as error:
        adapter.FreeCADBackend().build(make_job(tmp_path, verbose=True))
    assert error.value.code == "geometry"
    assert "child stdout" in error.value.diagnostics
    assert "child stderr" in error.value.diagnostics
    assert "Traceback" in error.value.diagnostics


def test_failed_snapshot_copy_removes_partial_file(tmp_path, monkeypatch):
    staging = tmp_path / ".autoblade-test"
    staging.mkdir()
    write_fcstd(staging / "failed.FCStd")

    def partial_copy(source, target):
        target.write(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(artifacts.shutil, "copyfileobj", partial_copy)
    with pytest.raises(OSError, match="disk full"):
        artifacts.preserve_failed_model(staging, tmp_path / "blade.FCStd")
    assert not list(tmp_path.glob("*_failed_*.FCStd"))


def test_invalid_output_directory_is_structured_before_launch(
    tmp_path, fake_backend, monkeypatch
):
    output = tmp_path / "file"
    output.write_text("existing file")
    monkeypatch.setattr(
        adapter, "run_process", lambda *a, **k: pytest.fail("CAD launched")
    )
    with pytest.raises(BackendError) as error:
        adapter.FreeCADBackend().build(make_job(output))
    assert error.value.code == "artifact_validation"
    assert output.read_text() == "existing file"


def test_closed_freecad_request_does_not_reread_mutable_inputs(tmp_path, fake_backend):
    from autoblade.adapters.cad.freecad.request import build_request

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    airfoil = inputs / "naca0012_sharp.csv"
    section = inputs / "blade_sections-naca.csv"
    shutil.copyfile(ROOT / "input/airfoils" / airfoil.name, airfoil)
    shutil.copyfile(ROOT / "input/blade_sections" / section.name, section)
    job = plan_create_job(
        airfoil.name,
        section.name,
        tmp_path / "output",
        airfoil_dir=inputs,
        blade_sections_dir=inputs,
        output_name_template="{blade}",
        author="",
        backend=BackendName.FREECAD,
    )
    expected = build_request(job.input_plan)
    airfoil.unlink()
    section.unlink()
    assert build_request(job.input_plan) == expected
    adapter.FreeCADBackend().build(job)
    assert all(path.exists() for path in job.output_paths)


def test_input_edit_during_parse_fails_before_cad(tmp_path):
    from autoblade.core.input_plan import build_blade_input_plan
    from autoblade.core.input_validation import read_airfoil_csv, InputValidationError

    source = tmp_path / "naca0012_sharp.csv"
    shutil.copyfile(ROOT / "input/airfoils" / source.name, source)

    def changing_reader(path):
        points = read_airfoil_csv(path)
        path.write_bytes(path.read_bytes() + b"\n")
        return points

    with pytest.raises(InputValidationError, match="input changed"):
        build_blade_input_plan(
            ROOT / "input/blade_sections/blade_sections-naca.csv",
            tmp_path,
            source.name,
            airfoil_reader=changing_reader,
        )
