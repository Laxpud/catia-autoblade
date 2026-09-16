"""显式启动阶段 2 FreeCADCmd 原型并只监督本次拥有的进程。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path

from .protocol import validate_curveswb_checkout, validate_request


def build_command(
    *,
    runner: Path,
    output_dir: Path,
) -> list[str]:
    """构造无 shell 的固定 Flatpak 命令，便于纯 Python 测试检查边界。"""
    return [
        "flatpak",
        "run",
        "--command=FreeCADCmd",
        "org.freecad.FreeCAD",
        "-u",
        str(output_dir / "user.cfg"),
        "-s",
        str(output_dir / "system.cfg"),
        str(runner),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the pinned FreeCAD Gordon prototype in an owned process."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--request", type=Path)
    source.add_argument("--rebuild-from", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--curveswb", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("blade.FCStd", "blade.stp", "result.json"):
        if (output_dir / filename).exists():
            parser.error(f"refusing to overwrite {output_dir / filename}")

    curveswb = args.curveswb.resolve(strict=True)
    validate_curveswb_checkout(curveswb)
    environment = os.environ.copy()
    environment.update(
        {
            "AUTOBLADE_PROTOTYPE_OUTPUT_DIR": str(output_dir),
            "AUTOBLADE_PROTOTYPE_CURVESWB_DIR": str(curveswb),
        }
    )
    if args.request is not None:
        request_path = args.request.resolve(strict=True)
        validate_request(json.loads(request_path.read_text(encoding="utf-8")))
        environment["AUTOBLADE_PROTOTYPE_REQUEST"] = str(request_path)
    else:
        rebuild_path = args.rebuild_from.resolve(strict=True)
        environment["AUTOBLADE_PROTOTYPE_REBUILD_FCSTD"] = str(rebuild_path)

    runner = Path(__file__).with_name("runner.py").resolve(strict=True)
    command = build_command(runner=runner, output_dir=output_dir)
    with (output_dir / "freecad.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            return_code = process.wait(timeout=args.timeout_seconds)
        except BaseException:
            # 只向本次新建的进程组发信号，绝不使用会影响用户 GUI 的 flatpak kill。
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise

    result_path = output_dir / "result.json"
    if not result_path.is_file():
        raise SystemExit(
            f"FreeCADCmd returned {return_code} without a structured result; "
            f"see {output_dir / 'freecad.log'}"
        )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    measurements = result.get("measurements", {})
    summary = {
        "status": result.get("status"),
        "request_source": result.get("request_source"),
        "request_sha256": result.get("request_sha256"),
        "dependency_fingerprint_sha256": result.get(
            "dependency_fingerprint_sha256"
        ),
        "solid": measurements.get("solid"),
        "reopen": measurements.get("reopen"),
        "artifacts": result.get("artifacts"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "peak_rss_kib": result.get("peak_rss_kib"),
        "error": result.get("error"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if return_code != 0 or result.get("status") != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
