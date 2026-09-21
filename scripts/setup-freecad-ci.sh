#!/usr/bin/env bash

# 只在 GitHub 的临时 Linux runner 中安装/锁定环境，禁止改写开发者已有 Flatpak。
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_OS:-}" != "Linux" ]]; then
    echo "This installer is restricted to an ephemeral GitHub Linux runner." >&2
    exit 1
fi
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mapfile -t pins < <(python3 - "$project_root/scripts/golden/ci-environment.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    data = json.load(stream)
for key in ("app_ref", "app_commit", "runtime_ref", "runtime_commit"):
    print(data[key])
PY
)
sudo apt-get update
sudo apt-get install -y flatpak dbus-x11
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user --noninteractive flathub "${pins[0]}" "${pins[2]}"
# 更新按完整 ref 限定，不能顺带更新另一个 pin。不可获取的历史 commit 直接报错。
flatpak update --user --noninteractive --no-deps --no-related --commit="${pins[1]}" "${pins[0]}"
flatpak update --user --noninteractive --no-deps --no-related --commit="${pins[3]}" "${pins[2]}"
[[ "$(flatpak info --user --show-commit "${pins[0]}")" == "${pins[1]}" ]]
[[ "$(flatpak info --user --show-commit "${pins[2]}")" == "${pins[3]}" ]]
