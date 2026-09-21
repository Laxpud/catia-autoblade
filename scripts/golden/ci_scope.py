"""为始终返回状态的 CI job 选择测量范围，避免路径过滤让 required check 永久等待。

只有确认整次变更与测量无关时才跳过 CAD。缺失比较基点或无法读取历史时执行
完整矩阵；定时和手动运行也始终执行完整矩阵。事件字段只传给 Git 参数，不作为
shell 代码执行；NUL 分隔的路径同时覆盖删除、重命名和带空格的文件名。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


def requires_measurement(event_name: str, event: dict) -> bool:
    """按 GitHub push/PR 的完整差异选择是否运行；无法确定时保守地测量。"""
    # 1. PR 比较分叉点以来的全部改动；push 比较推送前后的完整树。
    if event_name == "pull_request":
        base = event["pull_request"]["base"]["sha"]
        head = event["pull_request"]["head"]["sha"]
        separator = "..."
    elif event_name == "push":
        base, head = event.get("before", ""), event.get("after", "")
        separator = ".."
    else:
        return True
    if any(
        len(ref) != 40 or set(ref) - set("0123456789abcdef") or ref == "0" * 40
        for ref in (base, head)
    ):
        return True
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--name-only", "--no-renames", "-z",
             f"{base}{separator}{head}", "--"]
        )
    except subprocess.CalledProcessError:
        return True
    # 2. 覆盖后端、领域输入、Runner、夹具和构建环境；文档不启动真实 CAD。
    paths = [os.fsdecode(path) for path in diff.split(b"\0") if path]
    return any(
        path.startswith(("src/", "tests/", "scripts/", "input/", ".github/workflows/"))
        or path in {"pyproject.toml", "uv.lock", ".gitattributes", "config.toml"}
        for path in paths
    )


def main() -> None:
    """读取 runner 提供的事件文件，将稳定布尔输出交给 workflow 的步骤条件。"""
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    required = requires_measurement(os.environ["GITHUB_EVENT_NAME"], event)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(f"measure={str(required).lower()}\n")
    print(f"Full FreeCAD measurement required: {required}")


if __name__ == "__main__":
    main()
