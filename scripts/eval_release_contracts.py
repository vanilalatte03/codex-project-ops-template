#!/usr/bin/env python3
"""Replay the release safety and compatibility contracts in isolated snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

import eval_release


CONTRACTS = ("v1", "safety", "resume", "deps")
SUPPORTED = {"v1": ("v1", "v2"), "safety": ("v1", "v2"),
             "resume": ("v2",), "deps": ("v2",)}

V1_PROGRAM = r'''
import json
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from execute import StepExecutor

runner = StepExecutor("0-example")
path = Path("phases/0-example/index.json")
order = []
def complete(step, guardrails, command_context):
    order.append(step["step"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["steps"][step["step"]]["status"] = "completed"
    payload["steps"][step["step"]]["summary"] = "eval fixture completed"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return True
runner._execute_single_step = complete
runner._execute_all_steps("", "")
payload = json.loads(path.read_text(encoding="utf-8"))
print(json.dumps({"order": order, "statuses": [item["status"] for item in payload["steps"]],
                  "keys": sorted(payload.keys())}))
'''

SAFETY_PROGRAM = r'''
import contextlib
import io
import json
import sys
sys.path.insert(0, "scripts")
import guard

command = "git reset --" + "hard"
capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    guard.handle_policy("pre-tool-use", {"tool_input": {"command": command}})
result = json.loads(capture.getvalue())
print(json.dumps({"blocked": result.get("decision") == "block",
                  "permissionDenied": result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"}))
'''

TEST_SELECTORS = {
    "resume": [
        "scripts/tests/test_run_state.py",
        "scripts/tests/test_worktree.py::test_list_and_resume_reuse_same_owned_worktree_and_preserve_diagnostics",
        "scripts/tests/test_autopilot.py::test_merge_reconcile_skips_already_merged_pr",
    ],
    "deps": [
        "scripts/tests/test_dag.py",
        "scripts/tests/test_autopilot.py::test_parallel_branch_reconcile_preserves_prior_merge_and_current_task",
    ],
}


def evaluate(variant: str, scenario: str, repetition: int) -> dict:
    if variant not in eval_release.BASES or scenario not in CONTRACTS:
        raise ValueError("unknown variant or scenario")
    record = {
        "variant": variant, "scenario": f"EVAL-{scenario.upper()}", "repetition": repetition,
        "baseCommit": eval_release.BASES[variant],
        "environment": {"os": platform.platform(), "python": platform.python_version(),
                        "codex": None, "model": "not invoked", "effort": "not invoked",
                        "sandbox": "local isolated checkout"},
        "setupIncluded": False, "implementationRetryCount": 0, "reviewFixCount": 0,
        "humanInterventionCount": 0, "tokens": None,
        "unavailableReason": "No Codex call in this deterministic contract replay",
        "success": False, "firstPass": False, "evidence": [],
        "scope": "contract replay only; task PR review and per-sample CI are not included",
    }
    if variant not in SUPPORTED[scenario]:
        record.update(status="unsupported", fixtureSha256=None, wallTimeSeconds=None)
        return record
    program = V1_PROGRAM if scenario == "v1" else SAFETY_PROGRAM if scenario == "safety" else None
    source = program or "\n".join(TEST_SELECTORS[scenario])
    record["fixtureSha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()

    with tempfile.TemporaryDirectory(prefix="harness-release-contract-", ignore_cleanup_errors=True) as temp:
        checkout = Path(temp) / "checkout"
        eval_release.must_run(["git", "clone", "--quiet", "--no-hardlinks",
                               str(eval_release.ROOT), str(checkout)], eval_release.ROOT, timeout=120)
        eval_release.must_run(["git", "checkout", "--detach", eval_release.BASES[variant]], checkout)
        started = time.monotonic()
        if program:
            result = eval_release.run_command([sys.executable, "-B", "-c", program], checkout, timeout=90)
            try:
                observed = json.loads(result.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                observed = {}
            if scenario == "v1":
                record["contractPass"] = (
                    result.returncode == 0 and observed.get("order") == [0, 1]
                    and observed.get("statuses") == ["completed", "completed"]
                    and "tasks" not in observed.get("keys", [])
                )
            else:
                record["contractPass"] = (
                    result.returncode == 0 and observed.get("blocked") is True
                    and observed.get("permissionDenied") is True
                )
            record["observed"] = observed
        else:
            result = eval_release.run_command(
                [sys.executable, "-B", "-m", "pytest", "-q", *TEST_SELECTORS[scenario]],
                checkout, timeout=120,
            )
            record["contractPass"] = result.returncode == 0
            record["testSummary"] = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        record["wallTimeSeconds"] = round(time.monotonic() - started, 3)
        record["exitCode"] = result.returncode
        record["outputSha256"] = hashlib.sha256((result.stdout + result.stderr).encode("utf-8")).hexdigest()
        if result.returncode:
            record["errorSummary"] = (result.stderr or result.stdout)[-700:]
        record["status"] = "contract-pass" if record["contractPass"] else "contract-fail"
        record["firstPass"] = record["contractPass"]
        record["evidence"] = [f"output SHA-256 {record['outputSha256']}"]
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=eval_release.BASES, required=True)
    parser.add_argument("--scenario", choices=CONTRACTS, required=True)
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.repetition < 0:
        parser.error("repetition must be nonnegative; 0 is warm-up")
    result = evaluate(args.variant, args.scenario, args.repetition)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.get("contractPass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
