#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 /absolute/path/to/autoblade.whl" >&2
    exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wheel_path="$(realpath "$1")"
smoke_root="$(mktemp -d "$project_root/.test-tmp-wheel-smoke-linux.XXXXXX")"
venv_dir="$smoke_root/venv"
workspace_dir="$smoke_root/workspace"
library_workspace_dir="$smoke_root/library-workspace"

cleanup() {
    # 只清理由本脚本在仓库内创建、且名称带固定前缀的临时目录。
    case "$smoke_root" in
        "$project_root"/.test-tmp-wheel-smoke-linux.*)
            rm -rf -- "$smoke_root"
            ;;
        *)
            echo "Refusing to remove unexpected smoke path: $smoke_root" >&2
            ;;
    esac
}
trap cleanup EXIT

uv venv "$venv_dir" --python 3.14
python_executable="$venv_dir/bin/python"
autoblade_executable="$venv_dir/bin/autoblade"
create_executable="$venv_dir/bin/autoblade-create"
batch_executable="$venv_dir/bin/autoblade-batch"

PYTHONPATH= uv pip install --python "$python_executable" "$wheel_path"

PYTHONPATH= "$autoblade_executable" --help >/dev/null
PYTHONPATH= "$autoblade_executable" --version
for entrypoint in "$create_executable" "$batch_executable"; do
    PYTHONPATH= "$entrypoint" --help >/dev/null
    PYTHONPATH= "$entrypoint" --version
done

# Linux 安装只能得到 Windows marker 之外的依赖；核心导入、Parser 和 Planner
# 不得因此触发 pywin32 或任一 CAD 运行时。
PYTHONPATH= "$python_executable" - <<'PY'
from importlib import metadata, util
import sys

import autoblade
from autoblade.core import geometry, input_plan, input_validation, jobs, planner

assert metadata.version("autoblade") == autoblade.__version__
assert util.find_spec("catia_autoblade") is None
assert util.find_spec("pythoncom") is None
assert util.find_spec("win32com") is None
assert "pythoncom" not in sys.modules
assert "win32com" not in sys.modules
PY

PYTHONPATH= "$autoblade_executable" init "$workspace_dir" --with-examples
PYTHONPATH= "$autoblade_executable" init \
    "$library_workspace_dir" --with-airfoil-library
workspace_config="$workspace_dir/config.toml"
PYTHONPATH= "$autoblade_executable" --config "$workspace_config" list >/dev/null
PYTHONPATH= "$autoblade_executable" \
    --config "$workspace_config" config show >/dev/null

# 从旧用户目录读取必须先警告并仅预览；显式 apply 后新目录成为唯一来源，
# 旧活动文件被移除且原始字节保留在不覆盖的备份中。
config_home="$smoke_root/config-home"
legacy_config_dir="$config_home/catia-autoblade"
canonical_config="$config_home/autoblade/config.toml"
mkdir -p "$legacy_config_dir"
cp "$workspace_config" "$legacy_config_dir/config.toml"
(
    cd "$smoke_root"
    XDG_CONFIG_HOME="$config_home" PYTHONPATH= \
        "$autoblade_executable" config migrate >/dev/null
)
if [[ -e "$canonical_config" ]]; then
    echo "Configuration preview unexpectedly wrote the canonical file." >&2
    exit 1
fi
(
    cd "$smoke_root"
    XDG_CONFIG_HOME="$config_home" PYTHONPATH= \
        "$autoblade_executable" config migrate --apply >/dev/null
)
if [[ ! -f "$canonical_config" || -f "$legacy_config_dir/config.toml" ]]; then
    echo "Legacy user configuration location migration did not complete." >&2
    exit 1
fi
legacy_backups=("$legacy_config_dir"/config.toml.v4.0.0.bak*)
if [[ ${#legacy_backups[@]} -ne 1 || ! -f "${legacy_backups[0]}" ]]; then
    echo "Legacy user configuration backup was not created exactly once." >&2
    exit 1
fi

PYTHONPATH= "$python_executable" "$project_root/scripts/installed_wheel_smoke.py" \
    --workspace "$workspace_dir" \
    --library-workspace "$library_workspace_dir" \
    --repository-root "$project_root"

echo "Linux non-editable wheel smoke: PASS"
