#!/usr/bin/env python3
"""Run Harness steps through small PRs, read-only review, and safe merge."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTATION_REASONING_EFFORT = "medium"
REVIEW_REASONING_EFFORT = "xhigh"
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


def _resolve_codex_bin() -> str:
    candidates = ("codex.cmd", "codex.exe", "codex") if sys.platform == "win32" else ("codex",)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return candidates[0]


CODEX_BIN = _resolve_codex_bin()
CODEX_ENV_CONFIG = "shell_environment_policy.inherit=all"


class AutopilotError(RuntimeError):
    """Raised when the autopilot loop cannot safely continue."""


@dataclass(frozen=True)
class ReviewResult:
    passed: bool
    findings: list[str]
    summary: str = ""
    checks_passed: bool = True
    diff_passed: bool = True
    codex_passed: bool = True
    commands: tuple[str, ...] = ()

    def to_markdown(self) -> str:
        conclusion = self.summary or (
            "블로커 없음. 이 step PR은 merge 가능합니다."
            if self.passed
            else "블로커가 있어 merge하지 않습니다."
        )
        rows = [
            ("로컬 검증", self.checks_passed, "docs/COMMANDS.md 기준 명령"),
            ("diff 검사", self.diff_passed, "git diff --check"),
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

    def __init__(
        self,
        phase: str,
        *,
        base: str = "main",
        max_review_fixes: int = 2,
        unsafe: bool = False,
        root: Path = ROOT,
    ):
        self.phase = phase
        self.base = base
        self.max_review_fixes = max_review_fixes
        self.unsafe = unsafe
        self.root = Path(root)

    # --- command helpers ---

    def _run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        timeout: int | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess:
        result = subprocess.run(
            cmd,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
        if check and result.returncode != 0:
            raise AutopilotError(self._command_failure(cmd, result))
        return result

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return self._run(["git", *args], check=check)

    def _gh(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return self._run(["gh", *args], check=check)

    # --- public flow ---

    def run(self) -> str:
        self._ensure_preconditions()
        merged_prs: list[str] = []

        while True:
            step = self._next_pending_step()
            if step is None:
                return "\n".join(merged_prs) if merged_prs else f"No pending steps for {self.phase}."

            branch = self._step_branch(step)
            self._run_step(branch, step)
            pr_url = self._create_pr(branch, step)
            self._review_and_fix_until_passed(pr_url, branch, step)

            self._mark_ready_and_merge(pr_url)
            merged_prs.append(pr_url)
            self._sync_base()

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
            "--reasoning-effort",
            IMPLEMENTATION_REASONING_EFFORT,
        ]
        if self.unsafe:
            cmd.append("--unsafe")
        self._run(cmd, timeout=1800)

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

        commands = "\n".join(f"- `{command}`" for command in self._review_commands())
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
            f"- Codex 지능은 구현 `{IMPLEMENTATION_REASONING_EFFORT}`, 리뷰 `{REVIEW_REASONING_EFFORT}`로 실행합니다.\n"
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

    def _review_commands(self) -> tuple[str, ...]:
        return (
            "python scripts/checks.py --stage manual",
            f"git diff --check origin/{self.base}...HEAD",
        )

    def _mark_ready_and_merge(self, pr_url: str):
        self._gh("pr", "ready", pr_url)
        self._gh("pr", "merge", pr_url, "--squash", "--delete-branch")

    def _comment_review(self, pr_url: str, review: ReviewResult):
        self._gh("pr", "comment", pr_url, "--body", review.to_markdown(), check=False)

    def _comment_issue(self, issue: IssueRecord, body: str):
        if issue.github_url:
            self._gh("issue", "comment", issue.github_url, "--body", body, check=False)

    # --- review gate ---

    def _run_review_gate(self, step: dict) -> ReviewResult:
        findings: list[str] = []
        commands = self._review_commands()

        checks_cmd = [sys.executable, "scripts/checks.py", "--stage", "manual"]
        checks_result = self._run(checks_cmd, check=False)
        checks_passed = checks_result.returncode == 0
        if not checks_passed:
            findings.append(self._command_failure(checks_cmd, checks_result))

        diff_cmd = ["git", "diff", "--check", f"origin/{self.base}...HEAD"]
        diff_result = self._run(diff_cmd, check=False)
        diff_passed = diff_result.returncode == 0
        if not diff_passed:
            findings.append(self._command_failure(diff_cmd, diff_result))

        codex_review = self._run_codex_review(step)
        if not codex_review.passed:
            findings.extend(codex_review.findings or [codex_review.summary or "Codex 자체 리뷰 실패"])

        findings = _dedupe(findings)
        passed = checks_passed and diff_passed and codex_review.passed and not findings
        return ReviewResult(
            passed,
            findings,
            "블로커 없음. 이 step PR은 merge 가능합니다." if passed else "블로커가 있어 merge하지 않습니다.",
            checks_passed=checks_passed,
            diff_passed=diff_passed,
            codex_passed=codex_review.passed,
            commands=commands,
        )

    def _command_failure(self, cmd: list[str], result: subprocess.CompletedProcess) -> str:
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        return f"`{' '.join(cmd)}` 실패: {self._compact_output(output) or f'exit {result.returncode}'}"

    @staticmethod
    def _compact_output(output: str, *, max_chars: int = 1200) -> str:
        if len(output) <= max_chars:
            return output
        return output[:max_chars].rstrip() + "\n... output truncated ..."

    def _run_codex_review(self, step: dict) -> ReviewResult:
        prompt = self._codex_review_prompt(step)
        before_status = self._worktree_status()
        schema_path = self._write_review_output_schema()
        last_message_path = self._temporary_path(".txt")
        try:
            result = self._run(
                [
                    CODEX_BIN,
                    "exec",
                    "-c",
                    f'model_reasoning_effort="{REVIEW_REASONING_EFFORT}"',
                    "-c",
                    CODEX_ENV_CONFIG,
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(last_message_path),
                    "--json",
                    "-",
                ],
                check=False,
                timeout=1800,
                input_text=prompt,
            )
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
                            "-c",
                            f'model_reasoning_effort="{REVIEW_REASONING_EFFORT}"',
                            "-c",
                            CODEX_ENV_CONFIG,
                            "--json",
                            "<review-prompt>",
                        ],
                        result,
                    )
                ],
                "자체 리뷰 실행 실패",
                codex_passed=False,
            )
        parsed = self._parse_review_result(result.stdout) or self._parse_review_result(last_message)
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
        candidates = list(reversed([line.strip() for line in stdout.splitlines() if line.strip()]))
        if stdout.strip():
            candidates.append(stdout.strip())

        for candidate in candidates:
            parsed = self._try_parse_review_candidate(candidate)
            if parsed is not None:
                return parsed
        return None

    def _try_parse_review_candidate(self, candidate: str) -> ReviewResult | None:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
            if not match:
                match = re.search(r"(\{.*\})", candidate, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                return None

        return self._try_parse_review_payload(data)

    def _try_parse_review_payload(self, payload: object) -> ReviewResult | None:
        if isinstance(payload, str):
            return self._try_parse_review_candidate(payload)
        if isinstance(payload, list):
            for item in reversed(payload):
                nested = self._try_parse_review_payload(item)
                if nested is not None:
                    return nested
            return None
        if not isinstance(payload, dict):
            return None

        passed = payload.get("pass", payload.get("passed"))
        if isinstance(passed, str):
            passed = passed.lower() in {"true", "pass", "passed", "ok"}
        if isinstance(passed, bool):
            findings = payload.get("findings", [])
            if isinstance(findings, str):
                findings = [findings]
            if not isinstance(findings, list):
                findings = [str(findings)]
            summary = str(payload.get("summary", ""))
            return ReviewResult(passed, [str(item) for item in findings], summary, codex_passed=passed)

        for key in ("result", "message", "content", "final", "text", "value", "output", "item"):
            value = payload.get(key)
            if isinstance(value, (str, dict, list)):
                nested = self._try_parse_review_payload(value)
                if nested is not None:
                    return nested
        for value in payload.values():
            if isinstance(value, (str, dict, list)):
                nested = self._try_parse_review_payload(value)
                if nested is not None:
                    return nested
        return None

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

    def _invoke_codex_fix(self, issue: IssueRecord, branch: str, step: dict,
                          review: ReviewResult, attempt: int):
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
        self._run(
            [
                CODEX_BIN,
                "exec",
                "-c",
                f'model_reasoning_effort="{IMPLEMENTATION_REASONING_EFFORT}"',
                "-c",
                CODEX_ENV_CONFIG,
                "--json",
                "-",
            ],
            timeout=1800,
            input_text=prompt,
        )

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
        commands = "\n".join(self._review_commands())
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
            "- 로컬 검증, diff 검사, Codex 자체 리뷰를 모두 통과한다.\n"
        )

    # --- parsing ---

    @staticmethod
    def _extract_url(output: str) -> str:
        match = re.search(r"https?://\S+", output)
        return match.group(0) if match else output.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Harness phase as reviewed step PRs.")
    parser.add_argument("phase", help="Phase directory name, e.g. 0-mvp")
    parser.add_argument("--base", default="main", help="Base branch for PRs and merges")
    parser.add_argument(
        "--max-review-fixes",
        type=int,
        default=2,
        help="Maximum automatic fix attempts before leaving the PR and issue open",
    )
    parser.add_argument("--unsafe", action="store_true", help="Pass --unsafe to scripts/execute.py")
    args = parser.parse_args()

    try:
        pr_urls = AutopilotRunner(
            args.phase,
            base=args.base,
            max_review_fixes=args.max_review_fixes,
            unsafe=args.unsafe,
        ).run()
    except AutopilotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Autopilot completed: {pr_urls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
