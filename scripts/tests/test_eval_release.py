"""The release fixtures must fail before the task and pass after its target change."""

from __future__ import annotations

import subprocess
import sys

import eval_release


def _unittest_exit(root):
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "eval_tests"],
        cwd=root, capture_output=True, text=True, timeout=20,
    ).returncode


def test_docs_fixture_detects_only_the_intended_change(tmp_path):
    files = eval_release.fixture_files("docs")
    eval_release.write_files(tmp_path, files)

    assert _unittest_exit(tmp_path) != 0
    (tmp_path / "docs/STATUS.md").write_text("# 상태\n\n상태: 완료\n", encoding="utf-8")
    assert _unittest_exit(tmp_path) == 0


def test_code_fixture_detects_bug_and_boundary_fix(tmp_path):
    files = eval_release.fixture_files("code")
    eval_release.write_files(tmp_path, files)

    assert _unittest_exit(tmp_path) != 0
    (tmp_path / "eval_pkg/calc.py").write_text(
        "def clamp(value: int, low: int, high: int) -> int:\n"
        "    return max(low, min(value, high))\n", encoding="utf-8",
    )
    assert _unittest_exit(tmp_path) == 0


def test_fixture_hash_is_stable_and_excludes_variant():
    for scenario in eval_release.SCENARIOS:
        first = eval_release.fixture_hash(eval_release.fixture_files(scenario))
        second = eval_release.fixture_hash(eval_release.fixture_files(scenario))
        assert first == second
        assert len(first) == 64
