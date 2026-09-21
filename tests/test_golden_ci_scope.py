"""检查 required CI 的选择边界；本测试不启动 CAD 或访问 GitHub。"""

from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.golden import ci_scope


@pytest.mark.parametrize("path, expected", [
    (b"docs/testing.md", False),
    (b"src/autoblade/core/geometry.py", True),
    (b"tests/fixtures/golden/deleted.stp", True),
    (b"scripts/smoke_real_freecad.py", True),
    (b".gitattributes", True),
])
def test_push_scope_covers_complete_changed_paths(monkeypatch, path, expected):
    monkeypatch.setattr(ci_scope.subprocess, "check_output", lambda args: path + b"\0")
    assert ci_scope.requires_measurement(
        "push", {"before": "a" * 40, "after": "b" * 40}
    ) is expected


def test_pr_compares_all_changes_since_merge_base(monkeypatch):
    def diff(args):
        assert args[-2] == f"{'a' * 40}...{'b' * 40}"
        assert "--no-renames" in args
        return b"docs/a file.md\0src/autoblade/core/deleted.py\0"

    monkeypatch.setattr(ci_scope.subprocess, "check_output", diff)
    assert ci_scope.requires_measurement("pull_request", {
        "pull_request": {"base": {"sha": "a" * 40}, "head": {"sha": "b" * 40}}
    })


def test_unavailable_history_and_explicit_runs_do_not_skip_measurement(monkeypatch):
    def unavailable(args):
        raise subprocess.CalledProcessError(128, args)

    monkeypatch.setattr(ci_scope.subprocess, "check_output", unavailable)
    assert ci_scope.requires_measurement("push", {"before": "a" * 40, "after": "b" * 40})
    assert ci_scope.requires_measurement("push", {"before": "0" * 40, "after": "b" * 40})
    for event_name in ("schedule", "workflow_dispatch"):
        assert ci_scope.requires_measurement(event_name, {})
