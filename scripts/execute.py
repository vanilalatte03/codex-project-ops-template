#!/usr/bin/env python3
"""
Harness Step Executor — phase 내 step을 순차 실행하고 자가 교정한다.

Usage:
    python scripts/execute.py <phase-dir> [--push] [--branch <branch-name>]
"""

import argparse
import contextlib
import json
import subprocess
import sys
import threading
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import checks

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def progress_indicator(label: str):
    """터미널 진행 표시기. with 문으로 사용하며 .elapsed 로 경과 시간을 읽는다."""
    frames = "◐◓◑◒"
    stop = threading.Event()
    t0 = time.monotonic()

    def _animate():
        idx = 0
        while not stop.wait(0.12):
            sec = int(time.monotonic() - t0)
            sys.stderr.write(f"\r{frames[idx % len(frames)]} {label} [{sec}s]")
            sys.stderr.flush()
            idx += 1
        sys.stderr.write("\r" + " " * (len(label) + 20) + "\r")
        sys.stderr.flush()

    th = threading.Thread(target=_animate, daemon=True)
    th.start()
    info = types.SimpleNamespace(elapsed=0.0)
    try:
        yield info
    finally:
        stop.set()
        th.join()
        info.elapsed = time.monotonic() - t0


class StepExecutor:
    """Phase 디렉토리 안의 step들을 순차 실행하는 하네스."""

    MAX_RETRIES = 3
    FEAT_MSG = "feat: {phase} {num}단계 {name} 구현"
    CHORE_MSG = "chore: {phase} {num}단계 실행 기록 정리"
    COMPLETION_MSG = "chore: {phase} 완료 상태 기록"
    TZ = timezone(timedelta(hours=9))

    def __init__(self, phase_dir_name: str, *, auto_push: bool = False,
                 unsafe: bool = False, branch_name: Optional[str] = None,
                 step_number: Optional[int] = None,
                 next_step_only: bool = False):
        self._root = str(ROOT)
        self._phases_dir = ROOT / "phases"
        self._phase_dir = self._phases_dir / phase_dir_name
        self._phase_dir_name = phase_dir_name
        self._top_index_file = self._phases_dir / "index.json"
        self._auto_push = auto_push
        self._unsafe = unsafe
        self._branch_name = branch_name
        self._step_number = step_number
        self._next_step_only = next_step_only

        if not self._phase_dir.is_dir():
            print(f"ERROR: {self._phase_dir} not found")
            sys.exit(1)

        self._index_file = self._phase_dir / "index.json"
        if not self._index_file.exists():
            print(f"ERROR: {self._index_file} not found")
            sys.exit(1)

        idx = self._read_json(self._index_file)
        self._project = idx.get("project", "project")
        self._phase_name = idx.get("phase", phase_dir_name)
        self._total = len(idx["steps"])
        if self._branch_name is None:
            self._branch_name = f"codex/{self._phase_name}"

    def run(self):
        self._print_header()
        self._check_blockers()
        self._ensure_clean_worktree()
        self._checkout_branch()
        guardrails = self._load_guardrails()
        command_context = self._load_command_context()
        self._ensure_created_at()
        if self._step_number is not None or self._next_step_only:
            ran = self._execute_one_step(guardrails, command_context)
            if not ran:
                return
            if self._has_pending_steps():
                self._push_current_branch()
                print(f"\n  Step-only run completed for '{self._phase_name}'.")
                return
        else:
            self._execute_all_steps(guardrails, command_context)
        self._finalize()

    # --- timestamps ---

    def _stamp(self) -> str:
        return datetime.now(self.TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # --- JSON I/O ---

    @staticmethod
    def _read_json(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(p: Path, data: dict):
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- git ---

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        cmd = ["git"] + list(args)
        return subprocess.run(cmd, cwd=self._root, capture_output=True, text=True)

    def _ensure_clean_worktree(self):
        r = self._run_git("status", "--short", "--untracked-files=all")
        if r.returncode != 0:
            print("  ERROR: git status 확인 실패.")
            print(f"  {r.stderr.strip()}")
            sys.exit(1)

        status = r.stdout.strip()
        if not status:
            return

        print("  ERROR: 작업트리에 커밋되지 않은 변경사항이 있습니다.")
        print("  Harness는 unrelated 변경 커밋 방지를 위해 clean worktree에서만 실행합니다.")
        print("  변경사항을 commit 또는 stash한 뒤 다시 실행하세요.")
        print("\n  현재 변경사항:")
        for line in status.splitlines():
            print(f"    {line}")
        sys.exit(1)

    def _stage_existing_paths(self, *paths: str):
        existing = [path for path in paths if (Path(self._root) / path).exists()]
        if existing:
            self._run_git("add", "-A", "--", *existing)

    def _checkout_branch(self):
        branch = self._branch_name

        r = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            print(f"  ERROR: git을 사용할 수 없거나 git repo가 아닙니다.")
            print(f"  {r.stderr.strip()}")
            sys.exit(1)

        if r.stdout.strip() == branch:
            return

        r = self._run_git("rev-parse", "--verify", f"refs/heads/{branch}")
        r = self._run_git("checkout", branch) if r.returncode == 0 else self._run_git("checkout", "-b", branch)

        if r.returncode != 0:
            print(f"  ERROR: 브랜치 '{branch}' checkout 실패.")
            print(f"  {r.stderr.strip()}")
            print(f"  Hint: 변경사항을 stash하거나 commit한 후 다시 시도하세요.")
            sys.exit(1)

        print(f"  Branch: {branch}")

    def _commit_step(self, step_num: int, step_name: str):
        output_rel = f"phases/{self._phase_dir_name}/step{step_num}-output.json"
        index_rel = f"phases/{self._phase_dir_name}/index.json"

        self._run_git("add", "-A")
        self._run_git("reset", "HEAD", "--", output_rel)
        self._run_git("reset", "HEAD", "--", index_rel)

        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.FEAT_MSG.format(phase=self._phase_name, num=step_num, name=step_name)
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  Commit: {msg}")
            else:
                print(f"  WARN: 코드 커밋 실패: {r.stderr.strip()}")

        self._stage_existing_paths(output_rel, index_rel)
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.CHORE_MSG.format(phase=self._phase_name, num=step_num)
            r = self._run_git("commit", "-m", msg)
            if r.returncode != 0:
                print(f"  WARN: housekeeping 커밋 실패: {r.stderr.strip()}")

    # --- top-level index ---

    def _update_top_index(self, status: str):
        if not self._top_index_file.exists():
            return
        top = self._read_json(self._top_index_file)
        ts = self._stamp()
        for phase in top.get("phases", []):
            if phase.get("dir") == self._phase_dir_name:
                phase["status"] = status
                ts_key = {"completed": "completed_at", "error": "failed_at", "blocked": "blocked_at"}.get(status)
                if ts_key:
                    phase[ts_key] = ts
                break
        self._write_json(self._top_index_file, top)

    # --- guardrails & context ---

    def _load_guardrails(self) -> str:
        sections = []
        agents_md = ROOT / "AGENTS.md"
        if agents_md.exists():
            sections.append(f"## 프로젝트 규칙 (AGENTS.md)\n\n{agents_md.read_text()}")
        phase_dir = getattr(self, "_phase_dir", None)
        phase_readme = phase_dir / "README.md" if phase_dir is not None else None
        if phase_readme is not None and phase_readme.exists():
            sections.append(
                f"## 현재 Phase README ({getattr(self, '_phase_dir_name', phase_readme.parent.name)}/README.md)\n\n"
                f"{phase_readme.read_text()}"
            )
        docs_dir = ROOT / "docs"
        if docs_dir.is_dir():
            for doc in sorted(docs_dir.glob("*.md")):
                sections.append(f"## {doc.stem}\n\n{doc.read_text()}")
            adr_dir = docs_dir / "adr"
            if adr_dir.is_dir():
                for doc in sorted(adr_dir.glob("*.md")):
                    sections.append(f"## adr/{doc.stem}\n\n{doc.read_text()}")
        return "\n\n---\n\n".join(sections) if sections else ""

    def _load_command_context(self) -> str:
        selected = checks.collect_checks(ROOT, "manual")
        if not selected:
            return (
                "## 프로젝트 검증 명령\n\n"
                "`docs/COMMANDS.md`에 lint/test/build 명령이 아직 비어 있습니다. "
                "step 파일의 인수 기준에 명시된 검증을 우선 실행하고, "
                "프로젝트 명령이 확정되면 `docs/COMMANDS.md`를 갱신하세요.\n\n"
            )

        lines = "\n".join(f"{command.command}  # {command.name}" for command in selected)
        return (
            "## 프로젝트 검증 명령\n\n"
            "`docs/COMMANDS.md` 또는 `.codex/project-profile.json` 기준으로 아래 명령을 실행하세요.\n\n"
            "```bash\n"
            f"{lines}\n"
            "```\n\n"
        )

    @staticmethod
    def _build_step_context(index: dict) -> str:
        lines = [
            f"- Step {s['step']} ({s['name']}): {s['summary']}"
            for s in index["steps"]
            if s["status"] == "completed" and s.get("summary")
        ]
        if not lines:
            return ""
        return "## 이전 Step 산출물\n\n" + "\n".join(lines) + "\n\n"

    def _build_preamble(self, guardrails: str, step_context: str,
                        command_context: str = "",
                        prev_error: Optional[str] = None) -> str:
        commit_example = self.FEAT_MSG.format(
            phase=self._phase_name, num="N", name="<step-name>"
        )
        retry_section = ""
        if prev_error:
            retry_section = (
                f"\n## ⚠ 이전 시도 실패 — 아래 에러를 반드시 참고하여 수정하라\n\n"
                f"{prev_error}\n\n---\n\n"
            )
        return (
            f"당신은 {self._project} 프로젝트의 개발자입니다. 아래 step을 수행하세요.\n\n"
            f"{guardrails}\n\n---\n\n"
            f"{step_context}{retry_section}"
            f"{command_context}"
            f"## 작업 규칙\n\n"
            f"1. 이전 step에서 작성된 코드를 확인하고 일관성을 유지하라.\n"
            f"2. 이 step에 명시된 작업만 수행하라. 추가 기능이나 파일을 만들지 마라.\n"
            f"3. 기존 테스트를 깨뜨리지 마라.\n"
            f"4. AC(Acceptance Criteria)와 프로젝트 검증 명령을 직접 실행하라.\n"
            f"5. /phases/{self._phase_dir_name}/index.json의 해당 step status를 업데이트하라:\n"
            f"   - AC 통과 → \"completed\" + \"summary\" 필드에 이 step의 산출물을 한 줄로 요약\n"
            f"   - {self.MAX_RETRIES}회 수정 시도 후에도 실패 → \"error\" + \"error_message\" 기록\n"
            f"   - 사용자 개입이 필요한 경우 (API 키, 인증, 수동 설정 등) → \"blocked\" + \"blocked_reason\" 기록 후 즉시 중단\n"
            f"6. 모든 변경사항을 커밋하라:\n"
            f"   {commit_example}\n\n---\n\n"
        )

    # --- Codex 호출 ---

    def _invoke_codex(self, step: dict, preamble: str) -> dict:
        step_num, step_name = step["step"], step["name"]
        step_file = self._phase_dir / f"step{step_num}.md"

        if not step_file.exists():
            print(f"  ERROR: {step_file} not found")
            sys.exit(1)

        prompt = preamble + step_file.read_text()
        cmd = ["codex", "exec", "--json"]
        if self._unsafe:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        cmd.append(prompt)
        result = subprocess.run(
            cmd,
            cwd=self._root, capture_output=True, text=True, timeout=1800,
        )

        if result.returncode != 0:
            print(f"\n  WARN: Codex가 비정상 종료됨 (code {result.returncode})")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")

        output = {
            "step": step_num, "name": step_name,
            "exitCode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }
        out_path = self._phase_dir / f"step{step_num}-output.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        return output

    # --- 헤더 & 검증 ---

    def _print_header(self):
        print(f"\n{'='*60}")
        print(f"  Harness Step Executor")
        print(f"  Phase: {self._phase_name} | Steps: {self._total}")
        if self._auto_push:
            print(f"  Auto-push: enabled")
        print(f"{'='*60}")

    def _check_blockers(self):
        index = self._read_json(self._index_file)
        for s in reversed(index["steps"]):
            if s["status"] == "error":
                print(f"\n  ✗ Step {s['step']} ({s['name']}) failed.")
                print(f"  Error: {s.get('error_message', 'unknown')}")
                print(f"  Fix and reset status to 'pending' to retry.")
                sys.exit(1)
            if s["status"] == "blocked":
                print(f"\n  ⏸ Step {s['step']} ({s['name']}) blocked.")
                print(f"  Reason: {s.get('blocked_reason', 'unknown')}")
                print(f"  Resolve and reset status to 'pending' to retry.")
                sys.exit(2)
            if s["status"] != "pending":
                break

    def _ensure_created_at(self):
        index = self._read_json(self._index_file)
        if "created_at" not in index:
            index["created_at"] = self._stamp()
            self._write_json(self._index_file, index)

    # --- 실행 루프 ---

    def _execute_single_step(self, step: dict, guardrails: str, command_context: str) -> bool:
        """단일 step 실행 (재시도 포함). 완료되면 True, 실패/차단이면 False."""
        step_num, step_name = step["step"], step["name"]
        done = sum(1 for s in self._read_json(self._index_file)["steps"] if s["status"] == "completed")
        prev_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            index = self._read_json(self._index_file)
            step_context = self._build_step_context(index)
            preamble = self._build_preamble(guardrails, step_context, command_context, prev_error)

            tag = f"Step {step_num}/{self._total - 1} ({done} done): {step_name}"
            if attempt > 1:
                tag += f" [retry {attempt}/{self.MAX_RETRIES}]"

            with progress_indicator(tag) as pi:
                self._invoke_codex(step, preamble)
                elapsed = int(pi.elapsed)

            index = self._read_json(self._index_file)
            status = next((s.get("status", "pending") for s in index["steps"] if s["step"] == step_num), "pending")
            ts = self._stamp()

            if status == "completed":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["completed_at"] = ts
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                print(f"  ✓ Step {step_num}: {step_name} [{elapsed}s]")
                return True

            if status == "blocked":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["blocked_at"] = ts
                self._write_json(self._index_file, index)
                reason = next((s.get("blocked_reason", "") for s in index["steps"] if s["step"] == step_num), "")
                print(f"  ⏸ Step {step_num}: {step_name} blocked [{elapsed}s]")
                print(f"    Reason: {reason}")
                self._update_top_index("blocked")
                sys.exit(2)

            err_msg = next(
                (s.get("error_message", "Step did not update status") for s in index["steps"] if s["step"] == step_num),
                "Step did not update status",
            )

            if attempt < self.MAX_RETRIES:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "pending"
                        s.pop("error_message", None)
                self._write_json(self._index_file, index)
                prev_error = err_msg
                print(f"  ↻ Step {step_num}: retry {attempt}/{self.MAX_RETRIES} — {err_msg}")
            else:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "error"
                        s["error_message"] = f"[{self.MAX_RETRIES}회 시도 후 실패] {err_msg}"
                        s["failed_at"] = ts
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                print(f"  ✗ Step {step_num}: {step_name} failed after {self.MAX_RETRIES} attempts [{elapsed}s]")
                print(f"    Error: {err_msg}")
                self._update_top_index("error")
                sys.exit(1)

        return False  # unreachable

    def _execute_all_steps(self, guardrails: str, command_context: str):
        while True:
            index = self._read_json(self._index_file)
            pending = next((s for s in index["steps"] if s["status"] == "pending"), None)
            if pending is None:
                print("\n  All steps completed!")
                return

            step_num = pending["step"]
            for s in index["steps"]:
                if s["step"] == step_num and "started_at" not in s:
                    s["started_at"] = self._stamp()
                    self._write_json(self._index_file, index)
                    break

            self._execute_single_step(pending, guardrails, command_context)

    def _execute_one_step(self, guardrails: str, command_context: str) -> bool:
        step = self._select_single_step()
        if step is None:
            print("\n  No pending steps.")
            return False

        step_num = step["step"]
        index = self._read_json(self._index_file)
        for s in index["steps"]:
            if s["step"] == step_num and "started_at" not in s:
                s["started_at"] = self._stamp()
                self._write_json(self._index_file, index)
                break

        self._execute_single_step(step, guardrails, command_context)
        return True

    def _select_single_step(self) -> Optional[dict]:
        index = self._read_json(self._index_file)
        steps = index["steps"]
        pending = next((s for s in steps if s["status"] == "pending"), None)
        if pending is None:
            return None
        if self._next_step_only:
            return pending

        target = next((s for s in steps if s["step"] == self._step_number), None)
        if target is None:
            print(f"  ERROR: Step {self._step_number} not found.")
            sys.exit(1)
        if target["step"] != pending["step"]:
            print(
                f"  ERROR: Step {self._step_number} cannot run before "
                f"pending Step {pending['step']} ({pending['name']})."
            )
            sys.exit(1)
        if target.get("status") != "pending":
            print(f"  ERROR: Step {self._step_number} is not pending.")
            sys.exit(1)
        return target

    def _has_pending_steps(self) -> bool:
        index = self._read_json(self._index_file)
        return any(s.get("status") == "pending" for s in index["steps"])

    def _push_current_branch(self):
        if not self._auto_push:
            return
        branch = self._branch_name
        r = self._run_git("push", "-u", "origin", branch)
        if r.returncode != 0:
            print(f"\n  ERROR: git push 실패: {r.stderr.strip()}")
            sys.exit(1)
        print(f"  ✓ Pushed to origin/{branch}")

    def _finalize(self):
        index = self._read_json(self._index_file)
        index["completed_at"] = self._stamp()
        self._write_json(self._index_file, index)
        self._update_top_index("completed")

        self._stage_existing_paths(
            f"phases/{self._phase_dir_name}/index.json",
            "phases/index.json",
        )
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.COMPLETION_MSG.format(phase=self._phase_name)
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  ✓ {msg}")

        if self._auto_push:
            branch = self._branch_name
            r = self._run_git("push", "-u", "origin", branch)
            if r.returncode != 0:
                print(f"\n  ERROR: git push 실패: {r.stderr.strip()}")
                sys.exit(1)
            print(f"  ✓ Pushed to origin/{branch}")

        print(f"\n{'='*60}")
        print(f"  Phase '{self._phase_name}' completed!")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Harness Step Executor")
    parser.add_argument("phase_dir", help="Phase directory name (e.g. 0-mvp)")
    parser.add_argument("--push", action="store_true", help="Push branch after completion")
    parser.add_argument("--branch", help="Branch name to use instead of codex/<phase>")
    parser.add_argument("--unsafe", action="store_true", help="Run codex exec with sandbox and approval bypass")
    parser.add_argument("--step", type=int, help="Run only this pending step number")
    parser.add_argument("--next-step-only", action="store_true", help="Run only the next pending step")
    args = parser.parse_args()

    if args.step is not None and args.next_step_only:
        parser.error("--step and --next-step-only cannot be used together")

    StepExecutor(
        args.phase_dir,
        auto_push=args.push,
        unsafe=args.unsafe,
        branch_name=args.branch,
        step_number=args.step,
        next_step_only=args.next_step_only,
    ).run()


if __name__ == "__main__":
    main()
