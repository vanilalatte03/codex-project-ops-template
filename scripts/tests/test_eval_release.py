"""The release fixtures must fail before the task and pass after its target change."""

from __future__ import annotations

import subprocess
import sys
import json

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


def test_build_gate_parses_source_without_creating_bytecode(tmp_path):
    eval_release.write_files(tmp_path, eval_release.fixture_files("code"))
    profile = json.loads((tmp_path / ".codex/project-profile.json").read_text(encoding="utf-8"))
    command = profile["commands"]["build"][0]

    result = subprocess.run(command, cwd=tmp_path, shell=True, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.rglob("__pycache__"))


def test_capture_output_files_keeps_only_synthetic_task_files(tmp_path):
    eval_release.write_files(tmp_path, eval_release.fixture_files("code"))
    (tmp_path / "docs/private.txt").write_text("do not capture", encoding="utf-8")

    captured = eval_release.capture_output_files(tmp_path, "code")

    assert set(captured) == {"eval_pkg/calc.py", "eval_tests/__init__.py", "eval_tests/test_code.py"}
    assert captured["eval_pkg/calc.py"] == (tmp_path / "eval_pkg/calc.py").read_text(encoding="utf-8")
    assert "private.txt" not in str(captured)
