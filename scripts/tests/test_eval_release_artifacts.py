"""Replay commit-safe release evaluation outputs in PR CI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import eval_release


RESULTS = Path(__file__).resolve().parents[2] / "phases/harness-v2-modernization/eval-results"


@pytest.mark.parametrize("scenario", ["docs", "code"])
@pytest.mark.parametrize("variant", ["v1", "v2"])
def test_model_output_replays_acceptance(variant, scenario, tmp_path):
    record = json.loads((RESULTS / f"{variant}-{scenario}-reviewed-1.json").read_text(encoding="utf-8"))
    assert record["fixtureSha256"] == eval_release.fixture_hash(eval_release.fixture_files(scenario))
    assert record["baseCommit"] == eval_release.BASES[variant]
    assert record["localSuccess"] is True
    assert record["terminalStatus"] == "completed"
    assert record["scopePass"] is True
    assert record["outputFilesSha256"] == eval_release.fixture_hash(record["outputFiles"])

    initial = eval_release.fixture_files(scenario)
    allowed = {"docs/STATUS.md"} if scenario == "docs" else {
        "eval_pkg/calc.py", "eval_tests/__init__.py", "eval_tests/test_code.py"
    }
    assert set(record["outputFiles"]) == allowed
    eval_release.write_files(tmp_path, initial)
    eval_release.write_files(tmp_path, record["outputFiles"])
    if scenario == "docs":
        assert (tmp_path / "docs/STATUS.md").read_text(encoding="utf-8") == "# 상태\n\n상태: 완료\n"
    else:
        test = (tmp_path / "eval_tests/test_code.py").read_text(encoding="utf-8")
        assert "assertEqual" in test
    result = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "eval_tests"],
        cwd=tmp_path, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("scenario,variants", [
    ("compat", ("v1", "v2")), ("safety", ("v1", "v2")),
    ("resume", ("v2",)), ("deps", ("v2",)),
])
def test_contract_repetitions_pass(scenario, variants):
    for variant in variants:
        records = [
            json.loads((RESULTS / f"{variant}-{scenario}-run{repetition}.json").read_text(encoding="utf-8"))
            for repetition in range(4)
        ]
        assert [record["repetition"] for record in records] == [0, 1, 2, 3]
        assert len({record["fixtureSha256"] for record in records}) == 1
        assert all(record["contractPass"] is True for record in records)
        assert all(record["status"] == "contract-pass" for record in records)
