#!/usr/bin/env python3
"""Run an isolated, local Harness task sample without creating remote PRs."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BASES = {
    "v1": "a945f5bc9a64c40e97dcee18de91c4f59b39c7cb",
    "v2": "bcfadc383f0b1a599bca7a34b0eba73482d8cc41",
}
PHASE = "release-eval-fixture"
SCENARIOS = {
    "docs": {
        "task": "docs/STATUS.md의 '상태: 준비'를 '상태: 완료'로 바꿔라. 다른 문서와 제품 코드는 수정하지 마라.",
        "initial": {"docs/STATUS.md": "# 상태\n\n상태: 준비\n"},
        "tests": (
            "import pathlib\nimport unittest\n\n"
            "class StatusTest(unittest.TestCase):\n"
            "    def test_status_is_complete(self):\n"
            "        content = pathlib.Path('docs/STATUS.md').read_text(encoding='utf-8')\n"
            "        self.assertEqual(content, '# 상태\\n\\n상태: 완료\\n')\n"
        ),
        "allowed": ("docs/STATUS.md",),
    },
    "code": {
        "task": (
            "eval_pkg/calc.py의 clamp(value, low, high) 버그를 수정하고 "
            "eval_tests/에 경계값 회귀 테스트를 하나 이상 추가하라. 기존 시그니처를 유지하라."
        ),
        "initial": {
            "eval_pkg/calc.py": (
                "def clamp(value: int, low: int, high: int) -> int:\n"
                "    return min(low, max(value, high))\n"
            ),
        },
        "tests": (
            "import unittest\nfrom eval_pkg.calc import clamp\n\n"
            "class ClampTest(unittest.TestCase):\n"
            "    def test_inside(self):\n"
            "        self.assertEqual(clamp(5, 0, 10), 5)\n\n"
            "    def test_below(self):\n"
            "        self.assertEqual(clamp(-2, 0, 10), 0)\n"
        ),
        "allowed": ("eval_pkg/calc.py", "eval_tests/"),
    },
}


def run_command(args: list[str], cwd: Path, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=timeout)


def must_run(args: list[str], cwd: Path, *, timeout: int = 60) -> str:
    result = run_command(args, cwd, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{' '.join(args[:3])}: {result.stderr[-600:] or result.stdout[-600:]}")
    return result.stdout.strip()


def write_files(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def fixture_files(scenario: str) -> dict[str, str]:
    spec = SCENARIOS[scenario]
    profile = {
        "projectName": "harness-release-eval",
        "profile": "backend",
        "guardMode": "soft",
        "commands": {
            "test": ["python -m unittest discover -s eval_tests"],
            "build": ["python -m compileall -q eval_pkg"],
        },
    }
    step = (
        f"# 단계 0: eval-{scenario}\n\n"
        "## 읽어야 할 파일\n\n- /AGENTS.md\n- /docs/ARCHITECTURE.md\n"
        f"\n## 작업\n\n{spec['task']}\n\n"
        "## 인수 기준\n\n```powershell\n"
        "python scripts/checks.py --stage manual\n"
        "```\n\n## 금지사항\n\n- 지정된 파일 밖의 제품 코드를 수정하지 마라. 이유: 평가 범위가 고정돼 있다.\n"
    )
    files = {
        "AGENTS.md": (
            "# 평가용 프로젝트 규칙\n\n한국어로 작업한다. 현재 step만 구현한다. "
            "기존 테스트를 깨뜨리지 않는다. 민감정보를 기록하지 않는다.\n"
        ),
        "docs/ARCHITECTURE.md": (
            "# 평가용 아키텍처\n\nPython 표준 라이브러리와 로컬 파일만 사용한다. "
            "외부 API와 DB는 없다.\n"
        ),
        ".codex/project-profile.json": json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        ".codex/config.toml": 'model = "gpt-6-luna"\nsandbox_mode = "workspace-write"\n',
        "phases/index.json": json.dumps({"phases": [{"dir": PHASE, "status": "pending"}]}, indent=2) + "\n",
        f"phases/{PHASE}/README.md": f"# Phase: {PHASE}\n\n## 목표\n{spec['task']}\n",
        f"phases/{PHASE}/index.json": json.dumps(
            {"project": "harness-release-eval", "phase": PHASE,
             "steps": [{"step": 0, "name": f"eval-{scenario}", "status": "pending"}]},
            indent=2,
        ) + "\n",
        f"phases/{PHASE}/step0.md": step,
        f"phases/{PHASE}/docs-checks.json": json.dumps(
            {"paths": ["docs/STATUS.md"] if scenario == "docs" else ["docs/ARCHITECTURE.md"],
             "skipDirs": [], "skipSuffixes": [], "required": [], "finalRequired": [], "forbidden": []},
            indent=2,
        ) + "\n",
        "eval_pkg/__init__.py": "",
        "eval_tests/__init__.py": "",
        f"eval_tests/test_{scenario}.py": spec["tests"],
    }
    files.update(spec["initial"])
    return files


def fixture_hash(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode("utf-8") + b"\0" + content.encode("utf-8") + b"\0")
    return digest.hexdigest()


def evaluate(variant: str, scenario: str, repetition: int, *, execute: bool) -> dict:
    files = fixture_files(scenario)
    sha = fixture_hash(files)
    record = {
        "variant": variant,
        "scenario": f"EVAL-{scenario.upper()}",
        "repetition": repetition,
        "baseCommit": BASES[variant],
        "fixtureSha256": sha,
        "environment": {
            "os": platform.platform(), "python": platform.python_version(),
            "codex": "codex-cli 0.146.0", "model": "gpt-6-luna", "effort": "low",
            "sandbox": "workspace-write", "approvalPolicy": "CLI noninteractive",
        },
        "setupIncluded": False,
        "cacheState": "existing local CLI cache",
        "retryLimit": 3,
        "success": False,
        "firstPass": False,
        "implementationRetryCount": 0,
        "reviewFixCount": 0,
        "wallTimeSeconds": None,
        "humanInterventionCount": 0,
        "tokens": None,
        "unavailableReason": "Harness runner commit-safe output does not expose usage",
        "evidence": [],
        "scope": "local task and acceptance only; PR review and CI not run per sample",
    }
    if not execute:
        record["status"] = "fixture-only"
        return record

    with tempfile.TemporaryDirectory(prefix="harness-release-eval-") as temp:
        checkout = Path(temp) / "checkout"
        must_run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(checkout)], ROOT, timeout=120)
        must_run(["git", "checkout", "--detach", BASES[variant]], checkout)
        profile = json.loads((checkout / ".codex/project-profile.json").read_text(encoding="utf-8"))
        files[".codex/project-profile.json"] = json.dumps(
            {**profile, **json.loads(files[".codex/project-profile.json"])},
            ensure_ascii=False, indent=2,
        ) + "\n"
        write_files(checkout, files)
        must_run(["git", "add", "-A"], checkout)
        must_run(["git", "-c", "user.name=Harness Eval", "-c", "user.email=eval@example.invalid",
                  "commit", "-qm", "test: 고정 평가 fixture 준비"], checkout)
        fixture_head = must_run(["git", "rev-parse", "HEAD"], checkout)
        branch = f"codex/eval-{scenario}"
        must_run(["git", "switch", "-c", branch], checkout)
        started = time.monotonic()
        try:
            run = run_command(
                [sys.executable, "scripts/execute.py", PHASE, "--branch", branch,
                 "--next-step-only", "--codex-effort", "low"],
                checkout, timeout=420,
            )
            record["wallTimeSeconds"] = round(time.monotonic() - started, 3)
            record["exitCode"] = run.returncode
            record["runOutputSha256"] = hashlib.sha256(
                (run.stdout + run.stderr).encode("utf-8")
            ).hexdigest()
            if run.returncode:
                record["errorSummary"] = (run.stderr or run.stdout)[-700:]
        except subprocess.TimeoutExpired:
            record["wallTimeSeconds"] = round(time.monotonic() - started, 3)
            record["exitCode"] = 124
            record["errorSummary"] = "execute.py timeout after 420 seconds"

        index = json.loads((checkout / "phases" / PHASE / "index.json").read_text(encoding="utf-8"))
        record["terminalStatus"] = index["steps"][0]["status"]
        changed = must_run(["git", "diff", "--name-only", fixture_head, "HEAD"], checkout).splitlines()
        record["changedPaths"] = changed
        allowed = list(SCENARIOS[scenario]["allowed"])
        allowed += [f"phases/{PHASE}/", "phases/index.json"]
        record["scopePass"] = all(any(path == prefix or path.startswith(prefix) for prefix in allowed) for path in changed)
        check = run_command([sys.executable, "scripts/checks.py", "--stage", "manual"], checkout, timeout=120)
        record["acceptancePass"] = check.returncode == 0
        if scenario == "docs":
            record["expectedResultPass"] = (
                (checkout / "docs/STATUS.md").read_text(encoding="utf-8") == "# 상태\n\n상태: 완료\n"
            )
        else:
            record["expectedResultPass"] = record["acceptancePass"] and any(
                path.startswith("eval_tests/") for path in changed
            )
        record["localSuccess"] = (
            record.get("exitCode") == 0 and record["terminalStatus"] == "completed"
            and record["scopePass"] and record["acceptancePass"] and record["expectedResultPass"]
        )
        record["firstPass"] = record["localSuccess"] and not index["steps"][0].get("retries")
        record["evidence"] = [f"local fixture commit {fixture_head}", f"run output SHA-256 {record.get('runOutputSha256')}"]
        # EVALS.md success requires PR review and CI for this exact output. Those are not
        # inferred from local checks, so release-success stays false pending those gates.
        record["status"] = "pending-pr-gates" if record["localSuccess"] else "local-failed"
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=BASES, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.repetition < 0:
        parser.error("repetition must be nonnegative; 0 is warm-up")
    print(json.dumps(evaluate(args.variant, args.scenario, args.repetition, execute=args.execute),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
