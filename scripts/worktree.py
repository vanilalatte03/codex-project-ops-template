#!/usr/bin/env python3
"""Harness가 소유한 task별 Git worktree의 생성·재개·정리 lifecycle."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


OWNER = "codex-harness"
MARKER_FILENAME = "harness-worktree.json"
MARKER_SCHEMA_VERSION = 1
MAX_TASK_DIRECTORY_NAME_LENGTH = 80
# Git for Windows can reject a linked worktree before the OS long-path policy
# is consulted (for example, ``fatal: '$GIT_DIR' too big``). Keep a margin for
# the admin path and Git metadata instead of discovering this after ``add``.
MAX_WINDOWS_WORKTREE_PATH_LENGTH = 240
VALID_STATUSES = frozenset(
    {
        "created",
        "running",
        "implemented",
        "reviewing",
        "ready",
        "merged",
        "error",
        "blocked",
        "interrupted",
    }
)
PRESERVED_STATUSES = frozenset({"error", "blocked", "interrupted"})


class WorktreeLifecycleError(RuntimeError):
    """Worktree lifecycle를 안전하게 진행할 수 없을 때 발생한다."""


class WorktreeConflictError(WorktreeLifecycleError):
    """기존 branch, path 또는 admin entry와 충돌한다."""


class WorktreeOwnershipError(WorktreeLifecycleError):
    """Harness가 소유하지 않은 marker를 조작하려 했다."""


class StaleWorktreeError(WorktreeLifecycleError):
    """Git admin entry와 실제 worktree 상태가 어긋났다."""


class WorktreeCleanupError(WorktreeLifecycleError):
    """검증되지 않은 worktree를 정리하려 했다."""


@dataclass(frozen=True)
class WorktreeState:
    task_id: str
    phase: str
    branch: str
    worktree_path: Path
    base_ref: str
    base_sha: str
    status: str = "created"
    owner: str = OWNER
    schema_version: int = MARKER_SCHEMA_VERSION
    head_sha: str | None = None
    created_at: str = ""
    updated_at: str = ""
    last_error: str | None = None
    diagnostics: tuple[str, ...] = field(default_factory=tuple)
    resume_count: int = 0

    @property
    def path(self) -> Path:
        return self.worktree_path

    def to_payload(self) -> dict:
        payload = {
            "schemaVersion": self.schema_version,
            "owner": self.owner,
            "taskId": self.task_id,
            "phase": self.phase,
            "branch": self.branch,
            "worktreePath": str(self.worktree_path),
            "baseRef": self.base_ref,
            "baseSha": self.base_sha,
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.head_sha:
            payload["headSha"] = self.head_sha
        if self.last_error:
            payload["lastError"] = self.last_error
        if self.diagnostics:
            payload["diagnostics"] = list(self.diagnostics)
        if self.resume_count:
            payload["resumeCount"] = self.resume_count
        return payload

    @classmethod
    def from_payload(cls, payload: object, *, marker_path: Path) -> "WorktreeState":
        if not isinstance(payload, dict):
            raise WorktreeLifecycleError(f"marker가 object가 아닙니다: {marker_path}")

        def required_string(key: str) -> str:
            value = payload.get(key)
            if not isinstance(value, str) or not value:
                raise WorktreeLifecycleError(f"marker의 {key}가 비어 있습니다: {marker_path}")
            return value

        schema_version = payload.get("schemaVersion")
        if schema_version != MARKER_SCHEMA_VERSION:
            raise WorktreeLifecycleError(
                f"지원하지 않는 worktree marker schemaVersion={schema_version}: {marker_path}"
            )

        status = required_string("status")
        if status not in VALID_STATUSES:
            raise WorktreeLifecycleError(f"지원하지 않는 worktree 상태 {status!r}: {marker_path}")

        raw_path = required_string("worktreePath")
        path = Path(raw_path)
        if not path.is_absolute():
            raise WorktreeLifecycleError(f"worktreePath는 absolute path여야 합니다: {marker_path}")

        diagnostics = payload.get("diagnostics", [])
        if not isinstance(diagnostics, list) or not all(isinstance(item, str) for item in diagnostics):
            raise WorktreeLifecycleError(f"marker의 diagnostics가 올바르지 않습니다: {marker_path}")

        resume_count = payload.get("resumeCount", 0)
        if not isinstance(resume_count, int) or resume_count < 0:
            raise WorktreeLifecycleError(f"marker의 resumeCount가 올바르지 않습니다: {marker_path}")

        owner = required_string("owner")
        return cls(
            task_id=required_string("taskId"),
            phase=required_string("phase"),
            branch=required_string("branch"),
            worktree_path=path.resolve(strict=False),
            base_ref=required_string("baseRef"),
            base_sha=required_string("baseSha"),
            status=status,
            owner=owner,
            schema_version=schema_version,
            head_sha=payload.get("headSha") if isinstance(payload.get("headSha"), str) else None,
            created_at=required_string("createdAt"),
            updated_at=required_string("updatedAt"),
            last_error=payload.get("lastError") if isinstance(payload.get("lastError"), str) else None,
            diagnostics=tuple(diagnostics),
            resume_count=resume_count,
        )


@dataclass(frozen=True)
class WorktreeHandle:
    state: WorktreeState
    marker_path: Path

    @property
    def path(self) -> Path:
        return self.state.worktree_path

    @property
    def task_id(self) -> str:
        return self.state.task_id

    @property
    def branch(self) -> str:
        return self.state.branch


@dataclass(frozen=True)
class WorktreeRecord:
    state: WorktreeState
    marker_path: Path
    attached: bool
    stale: bool
    head_sha: str | None = None
    branch: str | None = None

    @property
    def path(self) -> Path:
        return self.state.worktree_path


@dataclass(frozen=True)
class CleanupResult:
    worktree_removed: bool
    branch_removed: bool
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _GitWorktreeEntry:
    path: Path
    head_sha: str | None
    branch: str | None


class WorktreeLifecycle:
    """하나의 primary checkout에서 Harness-owned linked worktree를 관리한다.

    이 객체는 primary checkout의 branch를 바꾸지 않는다. 생성은 ``git
    worktree add -b``로만 수행하고, 정리는 owner/status/head/clean 검증을
    모두 통과한 경우에만 non-force 명령으로 수행한다.
    """

    def __init__(
        self,
        root: Path,
        *,
        worktree_root: Path | None = None,
        clock: Callable[[], str] | None = None,
        git_timeout: int = 600,
    ):
        self.root = Path(root).resolve()
        self.worktree_root = (
            Path(worktree_root).resolve()
            if worktree_root is not None
            else (self.root.parent / ".codex-worktrees" / self.root.name).resolve()
        )
        if self.worktree_root == self.root or self.worktree_root.is_relative_to(self.root) or self.root.is_relative_to(self.worktree_root):
            raise WorktreeConflictError(
                "managed worktree root와 primary checkout은 서로 겹치면 안 됩니다: "
                f"primary={self.root}, managed={self.worktree_root}"
            )
        self.clock = clock or self._now
        self.git_timeout = git_timeout

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _run_git(
        self,
        *args: str,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = ["git", *args]
        try:
            result = subprocess.run(
                command,
                cwd=cwd or self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.git_timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorktreeLifecycleError(f"`{' '.join(command)}` 실행 실패: {exc}") from exc
        if check and result.returncode != 0:
            output = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
            )
            raise WorktreeLifecycleError(
                f"`{' '.join(command)}` 실패: {output or f'exit {result.returncode}'}"
            )
        return result

    def _git_path(self, name: str) -> Path:
        result = self._run_git("rev-parse", "--git-path", name)
        raw = Path(result.stdout.strip())
        return raw if raw.is_absolute() else (self.root / raw).resolve()

    @staticmethod
    def _safe_task_slug(task_id: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", task_id).strip(".-")
        if not slug:
            slug = "task"
        slug = slug[:MAX_TASK_DIRECTORY_NAME_LENGTH].rstrip(".-") or "task"
        if slug.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"COM[1-9]", slug.upper()):
            slug = f"task-{slug}"
        return slug

    def _managed_path(self, task_id: str, requested: Path | None) -> Path:
        path = requested or (self.worktree_root / self._safe_task_slug(task_id))
        path = Path(path).resolve(strict=False)
        managed_root = self.worktree_root.resolve(strict=False)
        if path == self.root or path == managed_root or not path.is_relative_to(managed_root):
            raise WorktreeConflictError(
                f"task worktree path는 managed worktree root 안이어야 합니다: {path}"
            )
        if os.name == "nt" and len(str(path)) > MAX_WINDOWS_WORKTREE_PATH_LENGTH:
            raise WorktreeConflictError(
                "Windows Git이 처리할 수 있는 안전한 worktree path 길이를 초과했습니다. "
                f"짧은 --worktree-root를 지정하세요 (length={len(str(path))}, "
                f"limit={MAX_WINDOWS_WORKTREE_PATH_LENGTH}): {path}"
            )
        return path

    def _worktree_entries(self) -> list[_GitWorktreeEntry]:
        result = self._run_git("worktree", "list", "--porcelain")
        entries: list[_GitWorktreeEntry] = []
        current_path: Path | None = None
        current_head: str | None = None
        current_branch: str | None = None

        def flush() -> None:
            nonlocal current_path, current_head, current_branch
            if current_path is not None:
                entries.append(_GitWorktreeEntry(current_path.resolve(strict=False), current_head, current_branch))
            current_path = None
            current_head = None
            current_branch = None

        for line in result.stdout.splitlines():
            if not line.strip():
                flush()
            elif line.startswith("worktree "):
                flush()
                current_path = Path(line[len("worktree ") :].strip())
            elif line.startswith("HEAD "):
                current_head = line[len("HEAD ") :].strip()
            elif line.startswith("branch "):
                ref = line[len("branch ") :].strip()
                current_branch = ref.removeprefix("refs/heads/")
        flush()
        return entries

    def _admin_dirs(self) -> list[Path]:
        admin_root = self._git_path("worktrees")
        if not admin_root.is_dir():
            return []
        return sorted(
            (path for path in admin_root.iterdir() if path.is_dir() and (path / "gitdir").is_file()),
            key=lambda path: str(path).casefold(),
        )

    def _marker_records(self) -> list[WorktreeRecord]:
        entries = self._worktree_entries()
        records: list[WorktreeRecord] = []
        for admin_dir in self._admin_dirs():
            marker_path = admin_dir / MARKER_FILENAME
            if not marker_path.is_file():
                continue
            try:
                payload = json.loads(marker_path.read_text(encoding="utf-8"))
                state = WorktreeState.from_payload(payload, marker_path=marker_path)
            except (OSError, json.JSONDecodeError, WorktreeLifecycleError):
                raise
            entry = next(
                (
                    item
                    for item in entries
                    if item.path == state.worktree_path and item.branch == state.branch
                ),
                None,
            )
            attached = entry is not None and state.worktree_path.exists()
            stale = not attached or entry is None or entry.branch != state.branch
            records.append(
                WorktreeRecord(
                    state=state,
                    marker_path=marker_path,
                    attached=attached,
                    stale=stale,
                    head_sha=entry.head_sha if entry else None,
                    branch=entry.branch if entry else None,
                )
            )
        return records

    def list(self) -> list[WorktreeRecord]:
        """현재 Harness marker와 stale 여부를 읽는다. Git admin은 변경하지 않는다."""
        return self._marker_records()

    def _find_admin_for_path(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        entries = self._worktree_entries()
        if not any(item.path == resolved for item in entries):
            raise WorktreeLifecycleError(f"생성한 worktree를 Git admin에서 확인할 수 없습니다: {resolved}")

        git_file = resolved / ".git"
        if git_file.is_file():
            raw = git_file.read_text(encoding="utf-8").strip()
            if raw.startswith("gitdir:"):
                admin = Path(raw[len("gitdir:") :].strip())
                if not admin.is_absolute():
                    admin = (resolved / admin).resolve()
                admin = admin.resolve(strict=False)
                if (admin / "gitdir").is_file():
                    return admin

        for admin_dir in self._admin_dirs():
            marker = admin_dir / MARKER_FILENAME
            if marker.exists():
                try:
                    payload = json.loads(marker.read_text(encoding="utf-8"))
                    state = WorktreeState.from_payload(payload, marker_path=marker)
                except (OSError, json.JSONDecodeError, WorktreeLifecycleError):
                    continue
                if state.worktree_path == resolved:
                    return admin_dir
        raise WorktreeLifecycleError(f"worktree admin directory를 찾지 못했습니다: {resolved}")

    @staticmethod
    def _assert_owner(state: WorktreeState, marker_path: Path) -> None:
        if state.owner != OWNER:
            raise WorktreeOwnershipError(
                f"Harness가 소유하지 않은 worktree marker입니다 (owner={state.owner!r}): {marker_path}"
            )

    def _resolve_base_sha(self, base_ref: str, base_sha: str | None) -> str:
        result = self._run_git("rev-parse", "--verify", f"{base_ref}^{{commit}}")
        resolved = result.stdout.strip()
        if not resolved:
            raise WorktreeLifecycleError(f"base ref의 SHA를 확인하지 못했습니다: {base_ref}")
        if base_sha is not None and resolved != base_sha:
            raise WorktreeConflictError(
                f"base ref와 base SHA가 다릅니다: {base_ref}={resolved}, marker/request={base_sha}"
            )
        return base_sha or resolved

    def _write_state(self, marker_path: Path, state: WorktreeState) -> None:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.to_payload(), ensure_ascii=False, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{MARKER_FILENAME}.", suffix=".tmp", dir=str(marker_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, marker_path)
        finally:
            Path(temp_name).unlink(missing_ok=True)

    def _handle_from_record(self, record: WorktreeRecord) -> WorktreeHandle:
        return WorktreeHandle(record.state, record.marker_path)

    def create_or_resume(
        self,
        *,
        task_id: str,
        phase: str,
        branch: str,
        base_ref: str,
        base_sha: str | None = None,
        path: Path | None = None,
    ) -> WorktreeHandle:
        """동일 task marker가 있으면 재사용하고, 없으면 새 linked worktree를 만든다."""
        if not task_id or not phase or not branch or not base_ref:
            raise WorktreeLifecycleError("task_id, phase, branch, base_ref는 필수입니다.")
        expected_path = self._managed_path(task_id, path)
        records = self._marker_records()

        same_task = [record for record in records if record.state.task_id == task_id]
        if len(same_task) > 1:
            raise WorktreeConflictError(f"task marker가 여러 개라 재개할 수 없습니다: {task_id}")
        if same_task:
            record = same_task[0]
            self._assert_owner(record.state, record.marker_path)
            state = record.state
            if (
                state.phase != phase
                or state.branch != branch
                or state.worktree_path != expected_path
                or state.base_ref != base_ref
                or (base_sha is not None and state.base_sha != base_sha)
            ):
                raise WorktreeConflictError(f"기존 task marker와 요청이 다릅니다: {task_id}")
            if state.status == "merged":
                raise WorktreeConflictError(f"이미 merged 상태인 task는 재사용할 수 없습니다: {task_id}")
            if record.stale:
                raise StaleWorktreeError(
                    f"stale worktree marker를 자동 복구하지 않습니다: {record.marker_path}"
                )
            object_exists = self._run_git(
                "cat-file",
                "-e",
                f"{state.base_sha}^{{commit}}",
                check=False,
            )
            if object_exists.returncode != 0:
                raise StaleWorktreeError(
                    f"marker의 pinned base SHA를 local object에서 찾지 못했습니다: {state.base_sha}"
                )
            return self._handle_from_record(record)

        resolved_base_sha = self._resolve_base_sha(base_ref, base_sha)
        entries = self._worktree_entries()
        for record in records:
            if record.state.worktree_path == expected_path or record.state.branch == branch:
                self._assert_owner(record.state, record.marker_path)
                raise WorktreeConflictError(
                    f"다른 task가 이미 사용하는 worktree path 또는 branch입니다: {expected_path} / {branch}"
                )
        for entry in entries:
            if entry.path == expected_path or entry.branch == branch:
                raise WorktreeConflictError(
                    f"기존 Git worktree와 충돌합니다 (path/branch): {expected_path} / {branch}"
                )
        if expected_path.exists():
            raise WorktreeConflictError(f"기존 path를 삭제하거나 덮어쓰지 않습니다: {expected_path}")
        branch_ref = f"refs/heads/{branch}"
        branch_exists = self._run_git("show-ref", "--verify", branch_ref, check=False)
        if branch_exists.returncode == 0:
            raise WorktreeConflictError(f"기존 branch를 재사용하거나 덮어쓰지 않습니다: {branch}")

        expected_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_git("worktree", "add", "-b", branch, str(expected_path), base_ref)

        try:
            admin_dir = self._find_admin_for_path(expected_path)
            now = self.clock()
            state = WorktreeState(
                task_id=task_id,
                phase=phase,
                branch=branch,
                worktree_path=expected_path,
                base_ref=base_ref,
                base_sha=resolved_base_sha,
                created_at=now,
                updated_at=now,
            )
            marker_path = admin_dir / MARKER_FILENAME
            self._write_state(marker_path, state)
            current_entries = self._worktree_entries()
            entry = next(
                (item for item in current_entries if item.path == expected_path and item.branch == branch),
                None,
            )
            if entry is None or entry.head_sha != resolved_base_sha:
                raise WorktreeLifecycleError(
                    f"생성 직후 worktree 검증 실패: path/branch/head={expected_path}/{branch}/{entry.head_sha if entry else None}"
                )
            return WorktreeHandle(state, marker_path)
        except Exception as exc:
            raise WorktreeLifecycleError(
                f"worktree marker/생성 검증에 실패했습니다. worktree는 진단을 위해 보존됩니다: {expected_path}; {exc}"
            ) from exc

    def _find_task_record(self, task_id: str) -> WorktreeRecord:
        matches = [record for record in self._marker_records() if record.state.task_id == task_id]
        if not matches:
            raise WorktreeLifecycleError(f"task marker를 찾지 못했습니다: {task_id}")
        if len(matches) > 1:
            raise WorktreeConflictError(f"task marker가 여러 개입니다: {task_id}")
        return matches[0]

    def resume(self, task_id: str) -> WorktreeHandle:
        record = self._find_task_record(task_id)
        self._assert_owner(record.state, record.marker_path)
        if record.stale:
            raise StaleWorktreeError(
                f"stale worktree를 자동 복구하지 않습니다. marker와 진단을 확인하세요: {record.marker_path}"
            )
        if record.state.status == "merged":
            raise WorktreeConflictError(f"이미 merged 상태인 task는 재개할 수 없습니다: {task_id}")
        return self.transition(
            self._handle_from_record(record),
            "running",
            resume_count=record.state.resume_count + 1,
        )

    def transition(
        self,
        handle: WorktreeHandle,
        status: str,
        *,
        head_sha: str | None = None,
        error: str | None = None,
        diagnostics: Iterable[str] = (),
        resume_count: int | None = None,
    ) -> WorktreeHandle:
        if status not in VALID_STATUSES:
            raise WorktreeLifecycleError(f"지원하지 않는 worktree 상태입니다: {status}")
        marker_path = handle.marker_path
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
            current = WorktreeState.from_payload(payload, marker_path=marker_path)
        except (OSError, json.JSONDecodeError, WorktreeLifecycleError) as exc:
            raise WorktreeLifecycleError(f"worktree marker를 읽지 못했습니다: {marker_path}: {exc}") from exc
        self._assert_owner(current, marker_path)
        merged_diagnostics = list(current.diagnostics)
        for item in diagnostics:
            if item and item not in merged_diagnostics:
                merged_diagnostics.append(str(item))
        updated = replace(
            current,
            status=status,
            updated_at=self.clock(),
            head_sha=head_sha or current.head_sha,
            last_error=error or current.last_error,
            diagnostics=tuple(merged_diagnostics),
            resume_count=current.resume_count if resume_count is None else resume_count,
        )
        self._write_state(marker_path, updated)
        return WorktreeHandle(updated, marker_path)

    def _record_cleanup_failure(self, handle: WorktreeHandle, message: str) -> None:
        try:
            self.transition(handle, handle.state.status, error=message, diagnostics=[message])
        except WorktreeLifecycleError:
            pass

    def safe_cleanup(
        self,
        handle: WorktreeHandle,
        *,
        expected_head_sha: str | None = None,
    ) -> CleanupResult:
        """merged + owned + clean + expected HEAD일 때만 non-force cleanup한다."""
        marker_path = handle.marker_path
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
            state = WorktreeState.from_payload(payload, marker_path=marker_path)
        except (OSError, json.JSONDecodeError, WorktreeLifecycleError) as exc:
            raise WorktreeCleanupError(f"cleanup marker를 읽지 못했습니다: {marker_path}: {exc}") from exc
        self._assert_owner(state, marker_path)
        if state.status != "merged":
            raise WorktreeCleanupError(
                f"merged 상태가 아니므로 cleanup하지 않습니다: {state.task_id} status={state.status}"
            )
        path = state.worktree_path.resolve(strict=False)
        managed_root = self.worktree_root.resolve(strict=False)
        if path == self.root or path == managed_root or not path.is_relative_to(managed_root):
            raise WorktreeCleanupError(f"managed worktree 밖의 path는 cleanup하지 않습니다: {path}")

        entries = self._worktree_entries()
        entry = next((item for item in entries if item.path == path), None)
        if entry is None or entry.branch != state.branch:
            message = f"Git admin entry가 stale 또는 branch 불일치라 cleanup하지 않습니다: {path}"
            self._record_cleanup_failure(handle, message)
            raise WorktreeCleanupError(message)
        if not path.is_dir():
            message = f"worktree path가 없어 cleanup하지 않습니다: {path}"
            self._record_cleanup_failure(handle, message)
            raise WorktreeCleanupError(message)

        status = self._run_git(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored",
            cwd=path,
            check=False,
        )
        if status.returncode != 0:
            message = f"worktree status를 확인하지 못해 cleanup하지 않습니다: {status.stderr.strip()}"
            self._record_cleanup_failure(handle, message)
            raise WorktreeCleanupError(message)
        status_lines = [line for line in status.stdout.splitlines() if line.strip()]
        if status_lines:
            kind = "ignored" if any(line.startswith("!!") for line in status_lines) else "dirty"
            message = f"{kind} 변경이 남아 있어 cleanup하지 않습니다: {'; '.join(status_lines[:8])}"
            self._record_cleanup_failure(handle, message)
            raise WorktreeCleanupError(message)

        current_head_result = self._run_git("rev-parse", "HEAD", cwd=path)
        current_head = current_head_result.stdout.strip()
        expected_head = expected_head_sha or state.head_sha
        if not expected_head:
            message = "merged marker에 expected head SHA가 없어 cleanup하지 않습니다"
            self._record_cleanup_failure(handle, message)
            raise WorktreeCleanupError(message)
        if current_head != expected_head or (entry.head_sha and entry.head_sha != expected_head):
            message = (
                f"HEAD가 expected SHA와 달라 cleanup하지 않습니다: current={current_head}, "
                f"admin={entry.head_sha}, expected={expected_head}"
            )
            self._record_cleanup_failure(handle, message)
            raise WorktreeCleanupError(message)

        remove_result = self._run_git("worktree", "remove", str(path), check=False)
        if remove_result.returncode != 0:
            output = "\n".join(
                part.strip() for part in (remove_result.stdout, remove_result.stderr) if part and part.strip()
            )
            message = f"worktree non-force remove 실패. path와 marker를 보존합니다: {output or remove_result.returncode}"
            self._record_cleanup_failure(handle, message)
            raise WorktreeCleanupError(message)

        diagnostics: list[str] = []
        branch_result = self._run_git("branch", "-d", state.branch, check=False)
        branch_removed = branch_result.returncode == 0
        if not branch_removed:
            output = "\n".join(
                part.strip() for part in (branch_result.stdout, branch_result.stderr) if part and part.strip()
            )
            diagnostics.append(f"Harness-owned local branch를 non-force 삭제하지 못했습니다: {output or branch_result.returncode}")
        return CleanupResult(True, branch_removed, tuple(diagnostics))

    def create_validation_worktree(self, *, base_ref: str, base_sha: str) -> Path:
        """base 검증용 detached checkout을 만든다.

        이 checkout은 task marker를 만들지 않는 ephemeral 상태다. 호출자는
        반드시 ``remove_validation_worktree``를 호출해야 하며, dirty 상태면
        remove가 실패해 진단을 보존한다.
        """
        self._resolve_base_sha(base_ref, base_sha)
        path = (self.worktree_root / f".base-validation-{base_sha[:12]}").resolve()
        if path == self.root or path == self.worktree_root.resolve(strict=False) or not path.is_relative_to(self.worktree_root.resolve(strict=False)):
            raise WorktreeConflictError(f"base validation path가 managed root 밖입니다: {path}")
        if path.exists():
            raise WorktreeConflictError(f"기존 base validation path를 덮어쓰지 않습니다: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run_git("worktree", "add", "--detach", str(path), base_ref)
        entries = self._worktree_entries()
        entry = next((item for item in entries if item.path == path), None)
        if entry is None or entry.head_sha != base_sha:
            raise WorktreeLifecycleError(f"base validation worktree 생성 검증 실패: {path}")
        return path

    def remove_validation_worktree(self, path: Path) -> None:
        path = Path(path).resolve(strict=False)
        status = self._run_git(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored",
            cwd=path,
            check=False,
        )
        if status.returncode != 0:
            raise WorktreeCleanupError(f"base validation status 확인 실패: {path}: {status.stderr.strip()}")
        if status.stdout.strip():
            raise WorktreeCleanupError(
                f"base validation worktree가 dirty라 보존합니다: {path}: {status.stdout.strip()}"
            )
        result = self._run_git("worktree", "remove", str(path), check=False)
        if result.returncode != 0:
            output = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
            )
            raise WorktreeCleanupError(f"base validation worktree remove 실패: {path}: {output}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List, resume, or safely clean Harness task worktrees.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="primary checkout")
    parser.add_argument("--worktree-root", type=Path, help="managed worktree root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list Harness markers and stale state")
    resume = subparsers.add_parser("resume", help="resume an existing task marker")
    resume.add_argument("task_id")
    cleanup = subparsers.add_parser("cleanup", help="safely clean a merged task worktree")
    cleanup.add_argument("task_id")
    cleanup.add_argument("--expected-head-sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lifecycle = WorktreeLifecycle(args.root, worktree_root=args.worktree_root)
    try:
        if args.command == "list":
            for record in lifecycle.list():
                print(
                    json.dumps(
                        {
                            **record.state.to_payload(),
                            "markerPath": str(record.marker_path),
                            "attached": record.attached,
                            "stale": record.stale,
                            "adminHeadSha": record.head_sha,
                        },
                        ensure_ascii=False,
                    )
                )
        elif args.command == "resume":
            print(json.dumps(lifecycle.resume(args.task_id).state.to_payload(), ensure_ascii=False))
        else:
            result = lifecycle.safe_cleanup(
                lifecycle._handle_from_record(lifecycle._find_task_record(args.task_id)),
                expected_head_sha=args.expected_head_sha,
            )
            print(json.dumps(result.__dict__, ensure_ascii=False))
        return 0
    except WorktreeLifecycleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
