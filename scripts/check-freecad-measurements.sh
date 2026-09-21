#!/usr/bin/env bash

# 从干净 wheel 执行公开案例测量；退出码只代表环境、制品和报告完整性。
# 数值偏差、截面提取缺口及模型适用性进入报告，不触发自动几何裁决。
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:?Usage: bash scripts/check-freecad-measurements.sh NEW_OUTPUT_DIRECTORY}"
mkdir -p "$(dirname "$output_dir")"
mkdir "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
cd "$project_root"
uv build --wheel --out-dir "$output_dir/dist"
uv venv "$output_dir/venv" --python 3.14
uv pip install --python "$output_dir/venv/bin/python" "$output_dir"/dist/*.whl
trap 'rm -rf -- "$output_dir/venv"' EXIT
python3 - "$project_root" "$output_dir" <<'PY'
import json
from pathlib import Path
import subprocess
import sys
project, output = map(Path, sys.argv[1:])
pins = json.loads((project / "scripts/golden/ci-environment.json").read_text())
actual = {}
for kind in ("app", "runtime"):
    actual[kind + "_commit"] = subprocess.check_output(
        ["flatpak", "info", "--show-commit", pins[kind + "_ref"]], text=True
    ).strip()
    if actual[kind + "_commit"] != pins[kind + "_commit"]:
        raise SystemExit(f"Unexpected Flatpak {kind} identity: {actual}")
(output / "environment.json").write_text(json.dumps({**pins, "actual": actual}, indent=2) + "\n")
PY
for manifest in tests/fixtures/golden/*/manifest.json; do
    case_dir="$(dirname "$manifest")"
    case_name="$(basename "$case_dir")"
    "$output_dir/venv/bin/python" -m scripts.golden.run \
        --case "$case_dir" --output "$output_dir/$case_name"
done
# 密集点与普通合成输入只做 FreeCAD 建模和性能记录，不在线连接 CATIA。
"$output_dir/venv/bin/python" -m scripts.golden.candidates prepare --output "$output_dir/synthetic-inputs"
"$output_dir/venv/bin/python" -m scripts.golden.candidates freecad \
    --matrix "$output_dir/synthetic-inputs" --output "$output_dir/synthetic-models"
