"""监督每任务的 Flatpak 进程组，输出只留在内存，绝不操作用户 CAD 会话。"""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

from ....core.backend import BackendError, BackendName


def run_process(
    command: list[str], *, env: dict[str, str], timeout: float
) -> tuple[int, str, str]:
    """捕获两个输出流；超时与中断都先清理 owned process，再向上层报告。"""
    try:
        process = subprocess.Popen(
            command,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
    except OSError as error:
        raise BackendError(
            BackendName.FREECAD, "unavailable", f"Cannot launch FreeCAD: {error}"
        ) from error
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr
    except BaseException as error:
        # 1. Flatpak --die-with-parent 与独占进程组共同约束后代的生命周期。
        # 2. 不能用 flatpak kill APP_ID，它会关闭同应用的用户 GUI 会话。
        try:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
        except Exception as cleanup:
            error.add_note(f"Owned FreeCAD process cleanup failed: {cleanup}")
            error.cleanup_failed = True
            raise error
        if isinstance(error, subprocess.TimeoutExpired):
            raise BackendError(
                BackendName.FREECAD,
                "timeout",
                f"FreeCAD timed out after {timeout:g} seconds.",
                diagnostics=stdout + "\n" + stderr,
            ) from error
        raise


def build_command(
    *, runner: Path, staging: Path, dependency: Path, app_id: str
) -> list[str]:
    """只传 argv，并显式授权 staging 写入和固定源码读取，不经过 shell。"""
    if sys.platform != "linux" or shutil.which("flatpak") is None:
        raise BackendError(
            BackendName.FREECAD,
            "unavailable",
            "FreeCAD requires Linux and the Flatpak launcher.",
        )
    return [
        "flatpak",
        "run",
        "--die-with-parent",
        "--command=FreeCADCmd",
        f"--filesystem={staging}",
        f"--filesystem={runner.parent}:ro",
        f"--filesystem={dependency}:ro",
        app_id,
        "-u",
        str(staging / "user.cfg"),
        "-s",
        str(staging / "system.cfg"),
        str(runner),
    ]


def child_environment(staging: Path, dependency: Path) -> dict[str, str]:
    """不继承上一次重建/override 请求；清除 Python 路径污染和用户模块缓存。"""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("AUTOBLADE_FREECAD_")
        and key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    env.update(
        {
            "AUTOBLADE_FREECAD_OUTPUT_DIR": str(staging),
            "AUTOBLADE_FREECAD_CURVESWB_DIR": str(dependency),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env
