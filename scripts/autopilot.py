#!/usr/bin/env python3
"""Run Harness steps through small PRs, read-only review, and safe merge."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import guard
from codex_common import (
    ALLOWED_CODEX_EFFORTS,
    CODEX_ENV_CONFIG,
    CODEX_EXEC_TIMEOUT,
    codex_base_cmd,
    codex_effort_config,
    configure_utf8_stdio,
    read_acceptance_commands,
    resolve_codex_bin,
    validate_codex_effort,
)

ROOT = Path(__file__).resolve().parent.parent
CODEX_BIN = resolve_codex_bin()
DEFAULT_STEP_EFFORT = "medium"
DEFAULT_REVIEW_EFFORT = "high"
DEFAULT_FIX_EFFORT = "medium"
DEFAULT_GIT_TIMEOUT = 600
DEFAULT_GH_TIMEOUT = 600
PR_CHECKS_TIMEOUT = 3600
# ready 직후에는 CI가 체크 런을 아직 만들지 못해 "no checks reported"가
# 일시적으로 나올 수 있다. grace 동안 재확인한 뒤에만 체크 없음으로 판단한다.
NO_CHECKS_GRACE_SECONDS = 60
NO_CHECKS_POLL_SECONDS = 15
SCOPE_RULES_FILENAME = "scope-rules.json"
LOCK_RELATIVE_PATH = Path(".codex") / "autopilot.lock"
REVIEW_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["pass", "summary", "findings"],
    "additionalProperties": False,
}


def shell_quote(value: str) -> str:
    if sys.platform.startswith("win"):
        return subprocess.list2cmdline([value])
    return shlex.quote(value)


FALLBACK_REVIEW_CHECK_COMMAND = f"{shell_quote(sys.executable)} scripts/checks.py --stage manual"


def detect_default_base(root: Path = ROOT) -> str:
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "main"
    ref = result.stdout.strip()
    if result.returncode == 0 and ref.startswith("origin/"):
        return ref[len("origin/") :]
    return "main"


class AutopilotError(RuntimeError):
    """Raised when the autopilot loop cannot safely continue."""


@dataclass(frozen=True)
class ReviewResult:
    passed: bool
    findings: list[str]
    summary: str = ""
    checks_passed: bool = True
    diff_passed: bool = True
    scope_passed: bool = True
    codex_passed: bool = True
    commands: tuple[str, ...] = ()

    def to_markdown(self) -> str:
        conclusion = self.summary or (
            "블로커 없음. 이 step PR은 merge 가능합니다."
            if self.passed
            else "블로커가 있어 merge하지 않습니다."
        )
        rows = [
            ("로컬 검증", self.checks_passed, "step 인수 기준 또는 docs/COMMANDS.md 기준 명령"),
            ("diff 검사", self.diff_passed, "git diff --check"),
            ("범위 규칙", self.scope_passed, "scope-rules.json 금지/허용 규칙"),
            ("자체 리뷰", self.codex_passed, "Codex read-only review"),
        ]
        lines = [
            "## 자체 리뷰",
            "",
            "| 항목 | 결과 | 비고 |",
            "| --- | --- | --- |",
        ]
        for name, passed, note in rows:
            lines.append(f"| {name} | {'통과' if passed else '실패'} | {note} |")

        if self.commands:
            lines.extend(["", "## 확인한 명령", "", "```bash"])
            lines.extend(self.commands)
            lines.append("```")

        lines.extend(["", "## 발견사항"])
        if self.findings:
            lines.extend(f"- {finding}" for finding in _dedupe(self.findings))
        else:
            lines.append("- 없음")

        lines.extend(["", "## 리뷰 결론", conclusion])
        return "\n".join(lines)


@dataclass(frozen=True)
class IssueRecord:
    number: int
    title: str
    body: str
    local_path: Path
    github_url: str


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


class AutopilotRunner:
    """Coordinates a Harness phase as a sequence of small reviewed PRs."""

    # 테스트 fixture가 금지 키워드 문자열을 포함하는 파일들. 스캐너 코드 자체는
    # 키워드를 갖지 않으므로 (.codex/scope-rules.json으로 외부화) 제외하지 않는다.
    FORBIDDEN_SCAN_EXCLUDED_PATHS = (
        "scripts/tests/test_autopilot.py",
        "scripts/tests/test_checks.py",
    )
    FORBIDDEN_SCAN_EXCLUDED_PREFIXES = (
        "issues/",
    )
    HUNK_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    STEP_OUTPUT_RE = re.compile(r"^phases/[^/]+/step\d+-output\.json$")

    def __init__(
        self,
        phase: str,
        *,
        base: str = "main",
        max_review_fixes: int = 2,
        unsafe: bool = False,
        step_effort: str = DEFAULT_STEP_EFFORT,
        review_effort: str = DEFAULT_REVIEW_EFFORT,
        fix_effort: str = DEFAULT_FIX_EFFORT,
        allow_xhigh: bool = False,
        dry_run: bool = False,
        max_steps: int | None = None,
        allow_no_checks: bool = False,
        skip_base_checks: bool = False,
        root: Path = ROOT,
    ):
        self.phase = phase
        self.base = base
        self.max_review_fixes = max_review_fixes
        self.unsafe = unsafe
        self.step_effort = validate_codex_effort(step_effort, allow_xhigh=allow_xhigh)
        self.review_effort = validate_codex_effort(review_effort, allow_xhigh=allow_xhigh)
        self.fix_effort = validate_codex_effort(fix_effort, allow_xhigh=allow_xhigh)
        self.allow_xhigh = allow_xhigh
        self.dry_run = dry_run
        self.max_steps = max_steps
        self.allow_no_checks = allow_no_checks
        self.skip_base_checks = skip_base_checks
        self.root = Path(root)
        self._scope_rules_cache: dict | None = None
        self._global_scope_rules_cache: dict | None = None

    # --- command helpers ---

    def _run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        timeout: int | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=input_text,
            )
        except subprocess.TimeoutExpired as exc:
            raise AutopilotError(
                f"`{' '.join(cmd)}`가 {timeout}초 안에 끝나지 않아 중단했습니다."
            ) from exc
        if check and result.returncode != 0:
            raise AutopilotError(self._command_failure(cmd, result))
        return result

    def _run_shell(
        self,
        command: str,
        *,
        check: bool = True,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                command,
                cwd=self.root,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise AutopilotError(
                f"`{command}`가 {timeout}초 안에 끝나지 않아 중단했습니다."
            ) from exc
        if check and result.returncode != 0:
            raise AutopilotError(self._shell_command_failure(command, result))
        return result

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return self._run(["git", *args], check=check, timeout=DEFAULT_GIT_TIMEOUT)

    def _gh(
        self, *args: str, check: bool = True, timeout: int = DEFAULT_GH_TIMEOUT
    ) -> subprocess.CompletedProcess:
        return self._run(["gh", *args], check=check, timeout=timeout)

    # --- public flow ---

    def run(self) -> str:
        if self.dry_run:
            return self._dry_run_summary()

        self._acquire_lock()
        try:
            return self._run_loop()
        finally:
            self._release_lock()

    def _run_loop(self) -> str:
        self._ensure_preconditions()
        merged_prs: list[str] = []

        while True:
            if self.max_steps is not None and len(merged_prs) >= self.max_steps:
                return "\n".join(
                    merged_prs
                    + [f"--max-steps {self.max_steps} 도달. 남은 step은 다음 실행에서 처리합니다."]
                )

            step = self._next_pending_step()
            if step is None:
                self._run_final_gate()
                return "\n".join(merged_prs) if merged_prs else f"No pending steps for {self.phase}."

            branch = self._step_branch(step)
            self._run_step(branch, step)
            pr_url = self._create_pr(branch, step)
            self._review_and_fix_until_passed(pr_url, branch, step)

            self._mark_ready_and_merge(pr_url)
            merged_prs.append(pr_url)
            self._sync_base()

    def _dry_run_summary(self) -> str:
        index = self._load_phase_index()
        pending = [s for s in index.get("steps", []) if s.get("status") == "pending"]
        if not pending:
            return f"No pending steps for {self.phase}."
        if self.max_steps is not None:
            pending = pending[: self.max_steps]
        lines = [f"[dry-run] {self.phase}: {len(pending)}개 step을 실행 예정"]
        for step in pending:
            lines.append(
                f"[dry-run] Step {step.get('step')} `{step.get('name')}` -> {self._step_branch(step)}"
            )
        return "\n".join(lines)

    # --- concurrency lock ---

    def _lock_path(self) -> Path:
        return self.root / LOCK_RELATIVE_PATH

    def _acquire_lock(self):
        lock_path = self._lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._lock_is_stale(lock_path):
                    lock_path.unlink(missing_ok=True)
                    continue
                raise AutopilotError(
                    f"다른 autopilot 프로세스가 이미 실행 중입니다 (lock: {lock_path}). "
                    "동시 실행은 base 브랜치 상태를 깨뜨릴 수 있어 중단합니다."
                )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            return
        raise AutopilotError(f"lock 파일을 획득하지 못했습니다: {lock_path}")

    @staticmethod
    def _lock_is_stale(lock_path: Path) -> bool:
        try:
            pid = int(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return True
        if sys.platform.startswith("win"):
            if pid == os.getpid():
                return False
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                return True
            if result.stdout is None:
                return False
            return str(pid) not in result.stdout
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        return False

    def _release_lock(self):
        self._lock_path().unlink(missing_ok=True)

    def _review_and_fix_until_passed(self, pr_url: str, branch: str, step: dict) -> ReviewResult:
        issue: IssueRecord | None = None
        last_review: ReviewResult | None = None

        for attempt in range(self.max_review_fixes + 1):
            review = self._run_review_gate(step)
            last_review = review
            self._comment_review(pr_url, review)
            if review.passed:
                if issue is not None:
                    self._resolve_failure_issue(issue, review, step)
                return review

            if issue is None:
                issue = self._record_failure(pr_url, review, step)
            else:
                self._append_failure_attempt(issue, review, step, attempt)

            if attempt >= self.max_review_fixes:
                raise AutopilotError(
                    "자동 리뷰 수정 최대 횟수를 초과했습니다. PR과 Issue는 열린 상태로 유지합니다.\n"
                    f"PR: {pr_url}\n"
                    f"Issue: {issue.github_url or issue.local_path}\n"
                    f"마지막 결과: {last_review.summary}"
                )

            self._invoke_codex_fix(issue, branch, step, review, attempt + 1)
            self._commit_dirty_fix(step)
            self._push_branch(branch)

        raise AutopilotError(f"Step PR review gate failed: {pr_url}")

    # --- setup and step state ---

    def _ensure_preconditions(self):
        status = self._git("status", "--short", "--untracked-files=all").stdout.strip()
        if status:
            raise AutopilotError(
                "작업트리가 clean 상태가 아닙니다. 자동 PR 루프는 unrelated 변경 방지를 위해 중단합니다.\n"
                + status
            )

        self._gh("auth", "status")
        self._git("remote", "get-url", "origin")
        self._sync_base()
        if not self.skip_base_checks:
            self._ensure_base_checks_pass()

    def _ensure_base_checks_pass(self):
        # base가 이미 깨져 있으면 첫 step PR의 리뷰 gate가 step 실패처럼 보이는
        # 오인을 만든다. 루프 시작 전에 base에서 같은 검증을 돌려 fail-fast 한다.
        result = self._run_shell(FALLBACK_REVIEW_CHECK_COMMAND, check=False, timeout=CODEX_EXEC_TIMEOUT)
        if result.returncode != 0:
            raise AutopilotError(
                f"base 브랜치 `{self.base}`의 manual 검증이 이미 실패해서 자동 PR 루프를 시작하지 않습니다. "
                "base를 먼저 고치거나, 의도된 상태라면 --skip-base-checks로 이 검증을 생략할 수 있습니다.\n"
                + self._shell_command_failure(FALLBACK_REVIEW_CHECK_COMMAND, result)
            )

    def _sync_base(self):
        self._git("fetch", "origin", self.base)
        self._git("checkout", self.base)
        self._git("pull", "--ff-only", "origin", self.base)

    def _phase_index_path(self) -> Path:
        return self.root / "phases" / self.phase / "index.json"

    def _load_phase_index(self) -> dict:
        return json.loads(self._phase_index_path().read_text(encoding="utf-8"))

    def _next_pending_step(self) -> dict | None:
        index = self._load_phase_index()
        return next((s for s in index.get("steps", []) if s.get("status") == "pending"), None)

    def _step_branch(self, step: dict) -> str:
        return f"codex/{self.phase}-step{step['step']}-{step['name']}"

    # --- step execution and PR ---

    def _run_step(self, branch: str, step: dict):
        cmd = [
            sys.executable,
            "scripts/execute.py",
            self.phase,
            "--branch",
            branch,
            "--push",
            "--step",
            str(step["step"]),
            "--codex-effort",
            self.step_effort,
        ]
        if self.allow_xhigh:
            cmd.append("--allow-xhigh")
        if self.unsafe:
            cmd.append("--unsafe")
        self._run(cmd, timeout=CODEX_EXEC_TIMEOUT)

    def _create_pr(self, branch: str, step: dict) -> str:
        title = f"feat: {self.phase} {step['step']}단계 {step['name']} 구현"
        body = self._pr_body(branch, step)
        result = self._gh(
            "pr",
            "create",
            "--base",
            self.base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
            "--draft",
        )
        return self._extract_url(result.stdout) or branch

    def _pr_body(self, branch: str, step: dict) -> str:
        refreshed = self._step_from_index(step["step"]) or step
        summary = refreshed.get("summary") or "step 실행 결과를 phase index에 기록했습니다."
        task = self._step_task_summary(step)
        changed_files = self._changed_files()
        changed_section = "\n".join(f"- `{path}`" for path in changed_files[:12])
        if len(changed_files) > 12:
            changed_section += f"\n- 외 {len(changed_files) - 12}개 파일"
        if not changed_section:
            changed_section = "- 코드 변경 없음"

        commands = "\n".join(f"- `{command}`" for command in self._review_check_commands(step))
        return (
            "## 작업 내용\n"
            f"- `{self.phase}` Step {step['step']} `{step['name']}` 범위를 구현했습니다.\n"
            f"- 산출물: {summary}\n\n"
            "## 변경 이유\n"
            f"{self._pr_change_reason(summary, task)}\n\n"
            "## 주요 변경 사항\n"
            f"- Step 작업: {task}\n"
            f"{changed_section}\n\n"
            "## 테스트 및 확인\n"
            f"{commands}\n\n"
            "- Codex read-only review\n\n"
            "## 참고 사항\n"
            f"- 브랜치: `{branch}`\n"
            "- Draft PR로 생성하며 자체 리뷰 gate 통과 시 ready 전환 후 squash merge합니다.\n"
            f"- Codex 지능은 구현 `{self.step_effort}`, 리뷰 `{self.review_effort}`, 자동 fix `{self.fix_effort}`로 실행합니다.\n"
        )

    def _pr_change_reason(self, summary: str, task: str) -> str:
        task_text = self._sentence_fragment(task) or "현재 step"
        summary_text = self._sentence_fragment(summary) or "step 실행 결과를 반영함"
        return (
            f"- 이 PR은 \"{task_text}\" 요구사항을 완료하기 위한 변경입니다.\n"
            f"- 실제 변경 결과: {summary_text}."
        )

    @staticmethod
    def _sentence_fragment(text: str) -> str:
        return text.strip().rstrip(".")

    def _step_from_index(self, step_num: int) -> dict | None:
        index = self._load_phase_index()
        return next((s for s in index.get("steps", []) if s.get("step") == step_num), None)

    def _step_task_summary(self, step: dict) -> str:
        path = self.root / "phases" / self.phase / f"step{step['step']}.md"
        if not path.exists():
            return step["name"]
        in_task = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line == "## 작업":
                in_task = True
                continue
            if in_task and line.startswith("## "):
                break
            if in_task and line:
                return line.lstrip("- ")
        return step["name"]

    def _changed_files(self) -> list[str]:
        result = self._git("diff", "--name-only", f"origin/{self.base}...HEAD", check=False)
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    def _step_acceptance_commands(self, step: dict | None = None) -> tuple[str, ...]:
        step_number = self._step_number_from(step)
        if step_number is None:
            return (FALLBACK_REVIEW_CHECK_COMMAND,)

        path = self.root / "phases" / self.phase / f"step{step_number}.md"
        return read_acceptance_commands(path) or (FALLBACK_REVIEW_CHECK_COMMAND,)

    def _review_check_commands(self, step: dict | None = None) -> tuple[str, ...]:
        return (
            *self._step_acceptance_commands(step),
            f"git diff --check origin/{self.base}...HEAD",
        )

    @staticmethod
    def _is_diff_check_command(command: str) -> bool:
        return command.startswith("git diff --check")

    def _run_final_gate(self):
        commands = (
            f"{shell_quote(sys.executable)} scripts/checks.py --stage final",
            f"git diff --check origin/{self.base}...HEAD",
        )
        for command in commands:
            result = self._run_shell(command, check=False, timeout=CODEX_EXEC_TIMEOUT)
            if result.returncode != 0:
                raise AutopilotError(self._shell_command_failure(command, result))

    def _mark_ready_and_merge(self, pr_url: str):
        self._gh("pr", "ready", pr_url)
        self._wait_for_pr_checks(pr_url)
        self._gh("pr", "merge", pr_url, "--squash", "--delete-branch")

    def _wait_for_pr_checks(self, pr_url: str):
        deadline = time.monotonic() + NO_CHECKS_GRACE_SECONDS
        while True:
            result = self._gh(
                "pr",
                "checks",
                pr_url,
                "--watch",
                check=False,
                timeout=PR_CHECKS_TIMEOUT,
            )
            if result.returncode == 0:
                return
            output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
            if "no checks reported" not in output.lower():
                raise AutopilotError(
                    "PR 원격 체크가 통과하지 않아 merge하지 않습니다.\n"
                    f"PR: {pr_url}\n"
                    f"{self._compact_output(output) or f'exit {result.returncode}'}"
                )
            # "no checks reported"는 CI가 없는 저장소뿐 아니라 ready 직후
            # 체크 런 생성 전의 레이스에서도 나온다. grace 동안 재확인한다.
            if self.allow_no_checks:
                return
            if time.monotonic() >= deadline:
                print(
                    f"NOTICE: {NO_CHECKS_GRACE_SECONDS}초 동안 원격 체크가 나타나지 않아 "
                    "체크 없는 저장소로 판단하고 merge를 진행합니다. "
                    "CI가 없는 저장소라면 --allow-no-checks로 대기를 생략할 수 있습니다.",
                    file=sys.stderr,
                )
                return
            time.sleep(NO_CHECKS_POLL_SECONDS)

    def _comment_review(self, pr_url: str, review: ReviewResult):
        self._gh("pr", "comment", pr_url, "--body", review.to_markdown(), check=False)

    def _comment_issue(self, issue: IssueRecord, body: str):
        if issue.github_url:
            self._gh("issue", "comment", issue.github_url, "--body", body, check=False)

    # --- review gate ---

    def _run_review_gate(self, step: dict) -> ReviewResult:
        findings: list[str] = []
        commands = self._review_check_commands(step)

        checks_passed = True
        diff_passed = True
        for command in commands:
            # step 문서는 codex가 수정할 수 있는 입력이므로,
            # 인수 기준 명령도 실행 전에 위험 명령 정책을 통과해야 한다.
            danger = guard.danger_reason(command)
            if danger:
                checks_passed = False
                findings.append(f"인수 기준 명령이 위험 명령 정책에 차단되었습니다: {danger}")
                continue
            result = self._run_shell(command, check=False, timeout=CODEX_EXEC_TIMEOUT)
            if result.returncode != 0:
                if self._is_diff_check_command(command):
                    diff_passed = False
                else:
                    checks_passed = False
                findings.append(self._shell_command_failure(command, result))

        scope_findings = self._scan_scope_diff(step)
        findings.extend(scope_findings)
        scope_passed = not scope_findings

        codex_review = self._run_codex_review(step)
        if not codex_review.passed:
            findings.extend(codex_review.findings or [codex_review.summary or "Codex 자체 리뷰 실패"])

        findings = _dedupe(findings)
        passed = checks_passed and diff_passed and scope_passed and codex_review.passed and not findings
        return ReviewResult(
            passed,
            findings,
            "블로커 없음. 이 step PR은 merge 가능합니다." if passed else "블로커가 있어 merge하지 않습니다.",
            checks_passed=checks_passed,
            diff_passed=diff_passed,
            scope_passed=scope_passed,
            codex_passed=codex_review.passed,
            commands=commands,
        )

    def _command_failure(self, cmd: list[str], result: subprocess.CompletedProcess) -> str:
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        return f"`{' '.join(cmd)}` 실패: {self._compact_output(output) or f'exit {result.returncode}'}"

    def _shell_command_failure(self, command: str, result: subprocess.CompletedProcess) -> str:
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        return f"`{command}` 실패: {self._compact_output(output) or f'exit {result.returncode}'}"

    @staticmethod
    def _compact_output(output: str, *, max_chars: int = 1200) -> str:
        if len(output) <= max_chars:
            return output
        return output[:max_chars].rstrip() + "\n... output truncated ..."

    # --- scope rules ---

    def _scan_scope_diff(self, step: dict | None = None) -> list[str]:
        diff_cmd = ["git", "diff", "--unified=0", f"origin/{self.base}...HEAD"]
        result = self._git(*diff_cmd[1:], check=False)
        if result.returncode != 0:
            # diff 실패를 빈 finding으로 돌리면 scope gate가 검사 없이 통과한다.
            # 실패 자체를 finding으로 보고해 gate를 막는다.
            return [self._command_failure(diff_cmd, result)]

        findings: list[str] = []
        current_file = ""
        line_no = 0
        skipped_file = False
        for raw in result.stdout.splitlines():
            if raw.startswith("+++ b/"):
                current_file = raw[len("+++ b/") :]
                skipped_file = self._skip_scope_scan_file(current_file)
                line_no = 0
                continue
            if raw.startswith("@@ "):
                match = self.HUNK_RE.search(raw)
                line_no = int(match.group(1)) if match else 0
                continue
            if skipped_file or not current_file:
                continue
            if raw.startswith("+") and not raw.startswith("+++"):
                line = raw[1:]
                active_line = line_no
                line_no += 1
                if self._line_in_safe_section(current_file, active_line):
                    continue
                for message in self._forbidden_messages(line):
                    if self._is_allowed_scope_message(message, line, step):
                        continue
                    findings.append(f"{current_file}:{active_line}: {message}")
            elif raw.startswith("-") and not raw.startswith("---"):
                continue
            else:
                line_no += 1
        return findings

    def _forbidden_messages(self, line: str) -> list[str]:
        messages: list[str] = []
        lowered = line.lower()
        for rule in self._forbidden_rules():
            message = rule.get("message")
            if not isinstance(message, str) or not message:
                continue
            if self._rule_matches_line(rule, line, lowered):
                messages.append(message)
        return messages

    def _rule_matches_line(self, rule: dict, line: str, lowered: str) -> bool:
        trigger_any = self._scope_rule_strings(rule, "anySubstrings")
        trigger_lowered = self._scope_rule_strings(rule, "anyLowered")
        if not (any(s in line for s in trigger_any) or any(s in lowered for s in trigger_lowered)):
            return False

        requires_any = self._scope_rule_strings(rule, "requiresAnySubstrings")
        requires_lowered = self._scope_rule_strings(rule, "requiresAnyLowered")
        if (requires_any or requires_lowered) and not (
            any(s in line for s in requires_any) or any(s in lowered for s in requires_lowered)
        ):
            return False

        excludes_any = self._scope_rule_strings(rule, "excludesAnySubstrings")
        excludes_lowered = self._scope_rule_strings(rule, "excludesAnyLowered")
        if any(s in line for s in excludes_any) or any(s in lowered for s in excludes_lowered):
            return False

        return True

    def _forbidden_rules(self) -> list[dict]:
        return [
            *self._rule_entries(self._global_scope_rules(), "forbidden"),
            *self._rule_entries(self._scope_rules(), "extraForbidden"),
        ]

    def _scope_rules(self) -> dict:
        """phases/<phase>/scope-rules.json — phase별 금지/허용 규칙."""
        if self._scope_rules_cache is None:
            self._scope_rules_cache = self._load_scope_rules_file(
                self.root / "phases" / self.phase / SCOPE_RULES_FILENAME
            )
        return self._scope_rules_cache

    def _global_scope_rules(self) -> dict:
        """.codex/scope-rules.json — 모든 phase에 적용되는 금지 규칙."""
        if self._global_scope_rules_cache is None:
            self._global_scope_rules_cache = self._load_scope_rules_file(
                self.root / ".codex" / SCOPE_RULES_FILENAME
            )
        return self._global_scope_rules_cache

    @staticmethod
    def _load_scope_rules_file(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AutopilotError(f"{path} 파싱 실패: {exc}") from exc
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _rule_entries(config: dict, key: str) -> list[dict]:
        entries = config.get(key, [])
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]

    @staticmethod
    def _scope_rule_strings(rule: dict, key: str) -> list[str]:
        values = rule.get(key, [])
        if not isinstance(values, list):
            return []
        return [value for value in values if isinstance(value, str)]

    def _is_allowed_scope_message(self, message: str, line: str, step: dict | None) -> bool:
        lowered = line.lower()
        step_number = self._step_number_from(step)
        step_name = step.get("name") if isinstance(step, dict) else None
        for rule in self._rule_entries(self._scope_rules(), "allowedScopeMessages"):
            if rule.get("message") != message:
                continue
            steps = rule.get("steps")
            if isinstance(steps, list) and step_number is not None and step_number not in steps:
                continue
            step_names = self._scope_rule_strings(rule, "stepNames")
            if step_names and step_name not in step_names:
                continue
            forbids = self._scope_rule_strings(rule, "forbidsAnyLowered")
            if forbids and any(marker in lowered for marker in forbids):
                continue
            requires = self._scope_rule_strings(rule, "requiresAnyLowered")
            if requires and not any(marker in lowered for marker in requires):
                continue
            return True
        return False

    @staticmethod
    def _step_number_from(step: dict | None) -> int | None:
        if not isinstance(step, dict):
            return None
        number = step.get("step")
        return number if isinstance(number, int) else None

    def _skip_scope_scan_file(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return (
            normalized in self.FORBIDDEN_SCAN_EXCLUDED_PATHS
            # scope-rules.json은 정의상 금지 키워드를 담으므로 스캔에서 제외한다.
            or Path(normalized).name == SCOPE_RULES_FILENAME
            or any(normalized.startswith(prefix) for prefix in self.FORBIDDEN_SCAN_EXCLUDED_PREFIXES)
            or self.STEP_OUTPUT_RE.match(normalized) is not None
        )

    def _line_in_safe_section(self, path: str, line_no: int) -> bool:
        target = self.root / path
        if not target.exists() or line_no <= 0:
            return False
        try:
            lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return False
        if line_no > len(lines):
            return False
        in_code_block = False
        for index, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
            if index == line_no:
                return in_code_block
        return False

    # --- Codex read-only review ---

    def _run_codex_review(self, step: dict) -> ReviewResult:
        prompt = self._codex_review_prompt(step)
        before_status = self._worktree_status()
        schema_path = self._write_review_output_schema()
        last_message_path = self._temporary_path(".txt")
        try:
            cmd = [
                resolve_codex_bin(),
                "exec",
                *codex_effort_config(self.review_effort),
                "-c",
                CODEX_ENV_CONFIG,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(last_message_path),
                "--json",
                "-",
            ]
            result = self._run(cmd, check=False, timeout=CODEX_EXEC_TIMEOUT, input_text=prompt)
            last_message = (
                last_message_path.read_text(encoding="utf-8")
                if last_message_path.exists()
                else ""
            )
        finally:
            schema_path.unlink(missing_ok=True)
            last_message_path.unlink(missing_ok=True)
        after_status = self._worktree_status()
        if after_status != before_status:
            return ReviewResult(
                False,
                [
                    "Codex read-only review changed the worktree. "
                    f"Before: {before_status or 'clean'} / After: {after_status or 'clean'}"
                ],
                "자체 리뷰가 worktree를 변경했습니다.",
                codex_passed=False,
            )
        if result.returncode != 0:
            return ReviewResult(
                False,
                [
                    self._command_failure(
                        [
                            "codex",
                            "exec",
                            *codex_effort_config(self.review_effort),
                            "--json",
                            "<review-prompt>",
                        ],
                        result,
                    )
                ],
                "자체 리뷰 실행 실패",
                codex_passed=False,
            )
        parsed = self._review_from_text(last_message) or self._parse_review_result(result.stdout)
        if parsed is None:
            parsed = self._parse_native_review_text(last_message)
        if parsed is None:
            return ReviewResult(
                False,
                ["자체 리뷰 실행 오류: JSON 결과를 파싱하지 못했습니다."],
                "자체 리뷰 실행 오류",
                codex_passed=False,
            )
        return parsed

    def _write_review_output_schema(self) -> Path:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as file:
            json.dump(REVIEW_OUTPUT_SCHEMA, file)
            return Path(file.name)

    def _temporary_path(self, suffix: str) -> Path:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as file:
            return Path(file.name)

    def _worktree_status(self) -> str:
        result = self._git("status", "--short", "--untracked-files=all", check=False)
        if result.returncode != 0:
            return f"<git status failed: {self._compact_output(result.stderr.strip())}>"
        return result.stdout.strip()

    def _codex_review_prompt(self, step: dict) -> str:
        step_num = step.get("step", "?")
        step_name = step.get("name", "unknown")
        phase_readme = f"phases/{self.phase}/README.md"
        step_file = f"phases/{self.phase}/step{step_num}.md"
        python_bin = str(Path(sys.executable))
        return (
            "Read-only review only. Do not modify files. "
            f"Review the current branch diff against origin/{self.base} for Harness project rules. "
            f"Current Harness step is Step {step_num} `{step_name}`. "
            "Ignore generated review-failure records under issues/**; they are audit logs, not implementation changes. "
            f"Check {phase_readme} and {step_file} first, then AGENTS.md, docs/PRD.md, "
            "docs/ARCHITECTURE.md, docs/ADR.md, docs/adr/, and docs/COMMANDS.md. "
            "For intermediate step PRs, the current step file is the step-local review contract. "
            "Missing functionality assigned to future steps is not a blocker. "
            "Implementing future-step scope inside the current step is a blocker. "
            "Focus on blockers: bugs, missing tests, MVP scope violations, API or CLI contract violations, build/test risk. "
            f"The runner already executed local checks before this review. If you rerun Python checks on Windows, use `{python_bin}` "
            "instead of assuming `python` or `py` is available on PATH. "
            "Return only JSON with keys: pass (boolean), summary (string), findings (array of strings)."
        )

    def _parse_review_result(self, stdout: str) -> ReviewResult | None:
        """codex exec --json JSONL 스트림에서 마지막 agent 메시지의 JSON 결과를 읽는다.

        `--output-last-message` 파일이 우선이고, 이 파서는 그 fallback이다.
        알려진 이벤트 형태(item/message/msg 노드의 text·message·content[].text)만
        본다. 임의 키 재귀 탐색은 하지 않는다.
        """
        result: ReviewResult | None = None
        for raw in stdout.splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            parsed = self._review_from_payload(event)
            for text in self._agent_message_texts(event):
                parsed = self._review_from_text(text) or parsed
            if parsed is not None:
                result = parsed
        if result is not None:
            return result
        # JSONL이 아닌 단일(또는 pretty-printed) JSON 출력 fallback.
        return self._review_from_text(stdout)

    @staticmethod
    def _agent_message_texts(event: dict) -> list[str]:
        texts: list[str] = []
        for key in ("item", "message", "msg"):
            node = event.get(key)
            if not isinstance(node, dict):
                continue
            for text_key in ("text", "message"):
                value = node.get(text_key)
                if isinstance(value, str) and value.strip():
                    texts.append(value)
            content = node.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict):
                    value = part.get("text")
                    if isinstance(value, str) and value.strip():
                        texts.append(value)
        return texts

    def _review_from_text(self, text: str) -> ReviewResult | None:
        candidate = text.strip()
        if not candidate:
            return None
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
        if not match:
            match = re.search(r"(\{.*\})", candidate, re.DOTALL)
        if match:
            candidate = match.group(1)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return self._review_from_payload(payload)

    @staticmethod
    def _review_from_payload(payload: object) -> ReviewResult | None:
        if not isinstance(payload, dict):
            return None
        passed = payload.get("pass", payload.get("passed"))
        if isinstance(passed, str):
            passed = passed.lower() in {"true", "pass", "passed", "ok"}
        if not isinstance(passed, bool):
            return None
        findings = payload.get("findings", [])
        if isinstance(findings, str):
            findings = [findings]
        if not isinstance(findings, list):
            findings = [str(findings)]
        summary = str(payload.get("summary", ""))
        return ReviewResult(passed, [str(item) for item in findings], summary, codex_passed=passed)

    def _parse_native_review_text(self, text: str) -> ReviewResult | None:
        stripped = text.strip()
        if not stripped:
            return None

        findings = [
            line.strip()
            for line in stripped.splitlines()
            if re.match(r"^[-*]\s+\[P[0-3]\]", line.strip())
        ]
        if findings:
            return ReviewResult(False, findings, "자체 리뷰에서 발견사항을 보고했습니다.", codex_passed=False)

        lowered = stripped.lower()
        pass_markers = (
            "no issues found",
            "no findings",
            "블로커 없음",
            "발견사항 없음",
            "문제 없음",
        )
        if any(marker in lowered for marker in pass_markers):
            return ReviewResult(True, [], stripped, codex_passed=True)
        return None

    # --- issue recording ---

    def _record_failure(self, pr_url: str, review: ReviewResult, step: dict) -> IssueRecord:
        number = self._next_issue_number()
        title = f"{self.phase} step {step['step']} 자동 리뷰 실패 {number}"
        body = self._issue_body(pr_url, review, step)
        issue_dir = self.root / "issues" / self.phase
        issue_dir.mkdir(parents=True, exist_ok=True)
        local_path = issue_dir / f"issue-{number}.md"
        local_path.write_text(f"# Issue {number}: {title}\n\n{body}", encoding="utf-8")

        gh_result = self._gh("issue", "create", "--title", title, "--body", body, check=False)
        github_url = self._extract_url(gh_result.stdout) if gh_result.returncode == 0 else ""
        self._commit_issue_record(local_path, step)
        return IssueRecord(number, title, body, local_path, github_url)

    def _append_failure_attempt(self, issue: IssueRecord, review: ReviewResult, step: dict, attempt: int):
        body = (
            f"## 재시도 {attempt} 리뷰 실패\n\n"
            f"{review.to_markdown()}\n"
        )
        existing = issue.local_path.read_text(encoding="utf-8")
        issue.local_path.write_text(f"{existing.rstrip()}\n\n---\n\n{body}", encoding="utf-8")
        self._comment_issue(issue, body)
        self._commit_issue_record(issue.local_path, step)

    def _resolve_failure_issue(self, issue: IssueRecord, review: ReviewResult, step: dict):
        body = (
            "## 자동 수정 완료\n\n"
            "같은 PR 브랜치에서 자동 수정 후 리뷰 gate를 통과했습니다.\n\n"
            f"{review.to_markdown()}\n"
        )
        existing = issue.local_path.read_text(encoding="utf-8")
        issue.local_path.write_text(f"{existing.rstrip()}\n\n---\n\n{body}", encoding="utf-8")
        if issue.github_url:
            self._gh("issue", "close", issue.github_url, "--comment", body, check=False)
        self._commit_issue_record(issue.local_path, step, message_suffix="자동 리뷰 해결 기록")

    def _commit_issue_record(self, local_path: Path, step: dict, *, message_suffix: str = "자동 리뷰 실패 기록"):
        try:
            rel_path = local_path.relative_to(self.root)
        except ValueError:
            rel_path = local_path

        if self._git("add", "--", str(rel_path), check=False).returncode != 0:
            return
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return

        message = f"chore: {self.phase} {step['step']}단계 {message_suffix}"
        if self._git("commit", "-m", message, check=False).returncode == 0:
            self._git("push", check=False)

    def _invoke_codex_fix(
        self,
        issue: IssueRecord,
        branch: str,
        step: dict,
        review: ReviewResult,
        attempt: int,
    ):
        prompt = (
            "당신은 Harness step PR 자동 리뷰 수정 담당자입니다. "
            f"현재 브랜치 `{branch}`에서 같은 PR의 리뷰 실패만 수정하세요.\n\n"
            "## 작업 범위\n"
            f"- Phase: {self.phase}\n"
            f"- Step: {step['step']} `{step['name']}`\n"
            f"- Fix attempt: {attempt}/{self.max_review_fixes}\n"
            "- 새 브랜치나 새 PR을 만들지 마세요.\n"
            "- 기존 변경을 되돌리지 말고, 리뷰 finding을 해결하는 데 필요한 최소 변경만 하세요.\n"
            "- 현재 step 파일에 없는 미래 step 기능을 구현해서 리뷰를 통과시키지 마세요.\n"
            "- 미래 step 미구현 finding은 현재 step 범위 밖이면 구현으로 해결하지 마세요.\n"
            "- 커밋과 push는 autopilot runner가 처리하므로 직접 커밋하지 마세요.\n\n"
            "## Issue\n"
            f"{issue.body}\n\n"
            "## 현재 리뷰 결과\n"
            f"{review.to_markdown()}\n\n"
            "수정 후 가능한 검증을 실행하고, 수정한 파일은 working tree에 남겨두세요."
        )
        cmd = codex_base_cmd(self.fix_effort)
        # 프롬프트는 argv 대신 stdin으로 전달해서 ARG_MAX 한계를 피한다.
        cmd.append("-")
        self._run(cmd, timeout=CODEX_EXEC_TIMEOUT, input_text=prompt)

    def _commit_dirty_fix(self, step: dict):
        status = self._git("status", "--short", "--untracked-files=all").stdout.strip()
        if not status:
            return
        self._git("add", "-A")
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        msg = f"fix: {self.phase} {step['step']}단계 리뷰 이슈 수정"
        self._git("commit", "-m", msg)

    def _push_branch(self, branch: str):
        self._git("push", "-u", "origin", branch)

    def _next_issue_number(self) -> int:
        issue_dir = self.root / "issues" / self.phase
        if not issue_dir.is_dir():
            return 1
        numbers: list[int] = []
        for path in issue_dir.glob("issue-*.md"):
            match = re.match(r"issue-(\d+)\.md", path.name)
            if match:
                numbers.append(int(match.group(1)))
        return max(numbers, default=0) + 1

    def _issue_body(self, pr_url: str, review: ReviewResult, step: dict) -> str:
        commands = "\n".join(self._review_check_commands(step))
        return (
            "## 발생 위치\n"
            f"- Phase: {self.phase}\n"
            f"- Step: {step['step']} `{step['name']}`\n"
            f"- PR: {pr_url}\n\n"
            "## 재현 명령\n"
            "```bash\n"
            f"{commands}\n"
            "```\n\n"
            "## 핵심 에러\n"
            f"{review.to_markdown()}\n\n"
            "## 수정 방향\n"
            "- 같은 PR 브랜치에서 발견사항을 수정하고 같은 gate를 다시 통과시킨다.\n\n"
            "## 완료 기준\n"
            "- 로컬 검증, diff 검사, 범위 규칙, Codex 자체 리뷰를 모두 통과한다.\n"
        )

    # --- parsing ---

    @staticmethod
    def _extract_url(output: str) -> str:
        match = re.search(r"https?://\S+", output)
        # gh 출력이 URL을 괄호/마크다운으로 감쌀 수 있어 trailing `)`를 제거한다.
        return match.group(0).rstrip(")") if match else ""


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Run a Harness phase as reviewed step PRs.")
    parser.add_argument("phase", help="Phase directory name, e.g. 0-mvp")
    parser.add_argument("--base", help="Base branch for PRs and merges. Defaults to origin/HEAD, then main.")
    parser.add_argument(
        "--max-review-fixes",
        type=int,
        default=2,
        help="Maximum automatic fix attempts before leaving the PR and issue open",
    )
    parser.add_argument("--unsafe", action="store_true", help="Pass --unsafe to scripts/execute.py")
    parser.add_argument("--dry-run", action="store_true", help="Print pending step/branch plan without side effects")
    parser.add_argument("--max-steps", type=int, help="Maximum step PRs to merge in this run")
    parser.add_argument(
        "--allow-no-checks",
        action="store_true",
        help="Do not wait through the no-checks grace period for repositories without CI checks",
    )
    parser.add_argument(
        "--skip-base-checks",
        action="store_true",
        help="Skip the base-branch manual check verification before starting the PR loop",
    )
    parser.add_argument(
        "--step-effort",
        choices=ALLOWED_CODEX_EFFORTS,
        default=DEFAULT_STEP_EFFORT,
        help="Reasoning effort for step implementation calls",
    )
    parser.add_argument(
        "--review-effort",
        choices=ALLOWED_CODEX_EFFORTS,
        default=DEFAULT_REVIEW_EFFORT,
        help="Reasoning effort for read-only review calls",
    )
    parser.add_argument(
        "--fix-effort",
        choices=ALLOWED_CODEX_EFFORTS,
        default=DEFAULT_FIX_EFFORT,
        help="Reasoning effort for automatic fix calls",
    )
    parser.add_argument("--allow-xhigh", action="store_true", help="Allow xhigh reasoning effort")
    args = parser.parse_args(argv)

    for option, effort in (
        ("--step-effort", args.step_effort),
        ("--review-effort", args.review_effort),
        ("--fix-effort", args.fix_effort),
    ):
        try:
            validate_codex_effort(effort, allow_xhigh=args.allow_xhigh)
        except ValueError as exc:
            parser.error(f"{option}: {exc}")
    if args.max_steps is not None and args.max_steps < 1:
        parser.error("--max-steps must be greater than 0")

    base = args.base or detect_default_base()
    try:
        pr_urls = AutopilotRunner(
            args.phase,
            base=base,
            max_review_fixes=args.max_review_fixes,
            unsafe=args.unsafe,
            step_effort=args.step_effort,
            review_effort=args.review_effort,
            fix_effort=args.fix_effort,
            allow_xhigh=args.allow_xhigh,
            dry_run=args.dry_run,
            max_steps=args.max_steps,
            allow_no_checks=args.allow_no_checks,
            skip_base_checks=args.skip_base_checks,
        ).run()
    except AutopilotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: 사용자 중단으로 종료합니다.", file=sys.stderr)
        return 130

    print(f"Autopilot completed: {pr_urls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
