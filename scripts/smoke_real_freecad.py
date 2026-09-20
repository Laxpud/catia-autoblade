"""显式从非 editable wheel 验证 FreeCAD 三命令、重建、超时与中断。

本脚本不进入 pytest。调用者先安装候选 wheel，再把该环境的 Python 传给
``--python``；所有输入副本、日志与制品留在显式 output 目录供人工复查。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]


def instances() -> set[str]:
    """仅比较 Flatpak 实例身份，不终止或连接用户已存在的 CAD 会话。"""
    result = subprocess.run(
        ["flatpak", "ps", "--columns=instance,application"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        line for line in result.stdout.splitlines() if "org.freecad.FreeCAD" in line
    }


def wait_instances(expected: set[str]) -> None:
    """进程退出后等待 Flatpak 实例登记释放，避免把上一任务误作下一任务。"""
    deadline = time.monotonic() + 10
    while instances() != expected:
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"FreeCAD instances did not return to baseline: {instances()}"
            )
        time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTHONPATH"
    }
    # 不能 resolve venv 的 Python 符号链接，否则会丢失 pyvenv.cfg 所在目录。
    python = str(args.python.absolute())
    identity = subprocess.run(
        [python, "-c", "import autoblade; print(autoblade.__file__)"],
        cwd=output,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if "site-packages" not in Path(identity).parts:
        raise RuntimeError(f"Expected a non-editable wheel installation: {identity}")

    workspace = output / "workspace"
    airfoils = workspace / "input/airfoils"
    sections = workspace / "input/blade_sections"
    airfoils.mkdir(parents=True)
    sections.mkdir()
    for name in ("naca0012_sharp.csv", "sc1095.csv"):
        shutil.copyfile(ROOT / "input/airfoils" / name, airfoils / name)
    shutil.copyfile(
        ROOT / "input/blade_sections/blade_sections-naca.csv",
        sections / "blade_sections-naca.csv",
    )
    (workspace / "config.toml").write_text(
        'version = "4.0.0"\n[defaults]\nbackend = "freecad"\n', encoding="utf-8"
    )
    prefix = [python, "-m", "autoblade.cli", "--config", str(workspace / "config.toml")]
    cases = [
        ("doctor", ["doctor", "--backend", "freecad"], 0),
        (
            "create",
            [
                "create",
                "-a",
                "naca0012_sharp.csv",
                "-s",
                "blade_sections-naca.csv",
                "--verbose",
            ],
            0,
        ),
        (
            "batch",
            ["batch", "-a", "sc1095.csv", "-s", "blade_sections-naca.csv", "--verbose"],
            0,
        ),
        (
            "sweep",
            [
                "sweep",
                "-a",
                "naca0012_sharp.csv",
                "-a",
                "sc1095.csv",
                "-s",
                "blade_sections-naca.csv",
                "--verbose",
            ],
            0,
        ),
        (
            "timeout",
            [
                "create",
                "-a",
                "naca0012_sharp.csv",
                "-s",
                "blade_sections-naca.csv",
                "--timeout-seconds",
                "0.1",
            ],
            1,
        ),
    ]
    before = instances()
    records = []
    for name, options, expected in cases:
        if name != "doctor":
            options += ["-o", str(output / name)]
        command = prefix + options
        started = time.monotonic()
        result = subprocess.run(
            command,
            cwd=output,
            env=environment,
            text=True,
            capture_output=True,
            timeout=120,
        )
        (output / f"{name}.log").write_text(
            result.stdout + "\n" + result.stderr, encoding="utf-8"
        )
        if result.returncode != expected:
            raise RuntimeError(
                f"{name} returned {result.returncode}, expected {expected}; see {output / (name + '.log')}"
            )
        wait_instances(before)
        records.append(
            {
                "name": name,
                "command": command,
                "exit_code": result.returncode,
                "elapsed_seconds": time.monotonic() - started,
                "runner_results": [
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if line.startswith('{"schema_version": "autoblade.freecad/result/')
                ],
            }
        )

    # 从 FCStd 内嵌请求重建，不读 CSV；同一 Runner/依赖必须得到相同测量。
    source = next((output / "create").glob("*.FCStd"))
    rebuilt = output / "rebuild"
    rebuilt.mkdir()
    rebuild_code = """
import json, sys
from pathlib import Path
from autoblade.adapters.cad.freecad import adapter
from autoblade.adapters.cad.freecad.process import build_command, child_environment, run_process
source, output = (Path(value) for value in sys.argv[1:])
dependency = adapter.bundled_dependency()
env = child_environment(output, dependency)
env['AUTOBLADE_FREECAD_REBUILD_FCSTD'] = str(source)
command = build_command(runner=Path(adapter.__file__).with_name('runner.py'), staging=output, dependency=dependency, app_id='org.freecad.FreeCAD')
code, stdout, stderr = run_process(command, env=env, timeout=120)
print(stdout)
print(stderr, file=sys.stderr)
result = json.loads((output / 'result.json').read_text())
if code != 0 or result['status'] != 'passed':
    raise SystemExit(1)
"""
    rebuild = subprocess.run(
        [python, "-c", rebuild_code, str(source), str(rebuilt)],
        cwd=output,
        env=environment,
        text=True,
        capture_output=True,
        timeout=150,
    )
    (output / "rebuild.log").write_text(
        rebuild.stdout + "\n" + rebuild.stderr, encoding="utf-8"
    )
    if rebuild.returncode != 0:
        raise RuntimeError("Embedded-request rebuild failed; see rebuild.log")
    rebuilt_result = json.loads((rebuilt / "result.json").read_text())
    original = next(case for case in records if case["name"] == "create")[
        "runner_results"
    ][0]
    if (
        rebuilt_result["request_sha256"] != original["request_sha256"]
        or rebuilt_result["measurements"] != original["measurements"]
        or rebuilt_result["request_source"] != "embedded_fcstd_request"
    ):
        raise RuntimeError(
            "Embedded-request rebuild changed the request or geometry measurements."
        )
    records.append(
        {"name": "rebuild", "exit_code": 0, "runner_results": [rebuilt_result]}
    )

    wait_instances(before)

    # 中断使用耗时更长的公开 89 截面案例，等 Child 已启动后只向 Host 发 SIGINT。
    for name in ("airfoil1_sharp.csv", "airfoil2_sharp.csv", "airfoil3_sharp.csv"):
        shutil.copyfile(ROOT / "input/airfoils" / name, airfoils / name)
    shutil.copyfile(
        ROOT / "input/blade_sections/blade_sections-multi-airfoil.csv",
        sections / "blade_sections-multi-airfoil.csv",
    )
    command = prefix + [
        "create",
        "-s",
        "blade_sections-multi-airfoil.csv",
        "-o",
        str(output / "interrupt"),
    ]
    process = subprocess.Popen(
        command,
        cwd=output,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if instances() - before:
                break
            if process.poll() is not None:
                raise RuntimeError("Interrupt case exited before its child started.")
            time.sleep(0.1)
        else:
            raise RuntimeError("Interrupt case did not start a FreeCAD instance.")
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=20)
    except BaseException:
        # 最后保障只针对本脚本持有的 Host，Host 管理其独立 CAD 进程组。
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.communicate(timeout=20)
        raise
    (output / "interrupt.log").write_text(stdout + "\n" + stderr, encoding="utf-8")
    if process.returncode != 130:
        raise RuntimeError(f"Interrupt returned {process.returncode}, expected 130.")
    records.append(
        {"name": "interrupt", "exit_code": process.returncode, "command": command}
    )
    # Flatpak 的实例登记可稍晚于被 wait 回收的进程删除，留有限清理窗口。
    deadline = time.monotonic() + 10
    while instances() - before and time.monotonic() < deadline:
        time.sleep(0.1)
    after = instances()
    if after != before:
        raise RuntimeError(
            f"FreeCAD instance set changed: before={before}, after={after}"
        )
    if list(output.rglob(".autoblade-*")):
        raise RuntimeError("Staging directories remain after smoke.")
    files = [
        {
            "path": str(path.relative_to(output)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(output.rglob("*"))
        if path.suffix in {".FCStd", ".stp"}
    ]
    report = {
        "date": datetime.now(timezone.utc).isoformat(),
        "package_file": identity,
        "cases": records,
        "artifacts": files,
        "instances_before": sorted(before),
        "instances_after": sorted(after),
    }
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"FreeCAD wheel smoke passed: {output / 'summary.json'}")


if __name__ == "__main__":
    main()
