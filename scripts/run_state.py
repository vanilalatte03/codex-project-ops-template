"""Durable, local-only state for a single Harness task run.

The state directory lives below Git's administrative directory, never in a
phase artifact.  It is therefore available to a later Harness invocation but
cannot be accidentally staged with a task diff.  Prompt and response bodies
are deliberately not accepted by this module.  A runner thread identifier is
stored only in this local operational state when it is needed to resume a
runner; public/commit-safe records omit it.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping


RUN_STATE_SCHEMA_VERSION = 1
RUN_STATUSES = frozenset(
    {"created", "running", "implemented", "reviewing", "ready", "merged", "error", "blocked", "interrupted"}
)
TERMINAL_STATUSES = frozenset({"merged"})
PRESERVED_STATUSES = frozenset({"error", "blocked", "interrupted"})
_TRANSITIONS = {
    "created": frozenset({"running", "error", "blocked", "interrupted"}),
    "running": frozenset({"implemented", "error", "blocked", "interrupted"}),
    "implemented": frozenset({"reviewing", "ready", "error", "blocked", "interrupted"}),
    "reviewing": frozenset({"ready", "error", "blocked", "interrupted"}),
    "ready": frozenset({"merged", "error", "blocked", "interrupted"}),
    "error": frozenset({"running"}),
    "blocked": frozenset({"running"}),
    "interrupted": frozenset({"running"}),
    "merged": frozenset(),
}
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|authorization|credential|secret|prompt|response)\b"
    r"\s*[:=]\s*([^\s,;]+)"
)
_MAX_DIAGNOSTIC_LENGTH = 512
_METRIC_FIELDS = frozenset(
    {
        "implementationRetryCount",
        "reviewFixCount",
        "wallTimeSeconds",
        "humanInterventionCount",
        "tokens",
        "unavailableReason",
    }
)


class RunStateError(RuntimeError):
    """A local run-state contract could not be safely satisfied."""


class RunStateCorruptionError(RunStateError):
    """A persisted state file is malformed and is preserved for diagnosis."""


class RunStateConflictError(RunStateError):
    """A task id was reused with a different immutable identity."""


class RunStateTransitionError(RunStateError):
    """An invalid lifecycle transition or duplicate action was requested."""


@dataclass(frozen=True)
class RunIdentity:
    phase: str
    task_id: str
    issue: int | None
    branch: str
    worktree_path: Path
    model: str | None = None
    effort: str | None = None

    def __post_init__(self) -> None:
        if not self.phase or not self.task_id or not self.branch:
            raise RunStateError("phase, task_id, branch는 비어 있을 수 없습니다")
        if self.issue is not None and (
            isinstance(self.issue, bool) or not isinstance(self.issue, int) or self.issue <= 0
        ):
            raise RunStateError("issue는 양의 정수 또는 None이어야 합니다")
        if not self.worktree_path.is_absolute():
            raise RunStateError("worktree_path는 absolute path여야 합니다")
        for name, value in (("model", self.model), ("effort", self.effort)):
            if value is not None and (not isinstance(value, str) or not value):
                raise RunStateError(f"{name}은 non-empty string 또는 None이어야 합니다")


@dataclass(frozen=True)
class RunState:
    identity: RunIdentity
    status: str = "created"
    attempt: int = 0
    thread_id: str | None = None
    process_id: int | None = None
    verification_status: str = "pending"
    review_status: str = "pending"
    metrics: Mapping[str, object] = field(default_factory=dict)
    completed_actions: Mapping[str, str] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    last_error: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_payload(self) -> dict:
        payload = {
            "schemaVersion": RUN_STATE_SCHEMA_VERSION,
            "phase": self.identity.phase,
            "taskId": self.identity.task_id,
            "issue": self.identity.issue,
            "branch": self.identity.branch,
            "worktreePath": str(self.identity.worktree_path),
            "model": self.identity.model,
            "effort": self.identity.effort,
            "status": self.status,
            "attempt": self.attempt,
            "verificationStatus": self.verification_status,
            "reviewStatus": self.review_status,
            "metrics": dict(self.metrics),
            "completedActions": dict(self.completed_actions),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.thread_id is not None:
            payload["threadId"] = self.thread_id
        if self.process_id is not None:
            payload["processId"] = self.process_id
        if self.diagnostics:
            payload["diagnostics"] = list(self.diagnostics)
        if self.last_error:
            payload["lastError"] = self.last_error
        return payload

    def to_public_record(self) -> dict:
        """Return a record suitable for a committed phase artifact or log."""
        return {
            "phase": self.identity.phase,
            "taskId": self.identity.task_id,
            "issue": self.identity.issue,
            "branch": self.identity.branch,
            "worktreePath": str(self.identity.worktree_path),
            "model": self.identity.model,
            "effort": self.identity.effort,
            "status": self.status,
            "attempt": self.attempt,
            "verificationStatus": self.verification_status,
            "reviewStatus": self.review_status,
            "metrics": dict(self.metrics),
            "completedActions": sorted(self.completed_actions),
            "diagnostics": list(self.diagnostics),
            "lastError": self.last_error,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def redact_text(value: str) -> str:
    """Redact common credential and prompt assignments before state persistence."""
    compact = value.strip()
    compact = _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", compact)
    if len(compact) > _MAX_DIAGNOSTIC_LENGTH:
        compact = compact[:_MAX_DIAGNOSTIC_LENGTH].rstrip() + "…"
    return compact


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        # Permission means the PID exists but belongs to another account.
        return exc.errno == errno.EPERM
    return True


class RunStateStore:
    """Atomic local state store keyed by a stable task identifier."""

    def __init__(
        self,
        directory: Path,
        *,
        clock: Callable[[], str] = _utc_now,
        process_exists: Callable[[int], bool] = _process_exists,
    ) -> None:
        self.directory = Path(directory).resolve(strict=False)
        self._clock = clock
        self._process_exists = process_exists

    @classmethod
    def for_repository(cls, root: Path, **kwargs) -> "RunStateStore":
        root = Path(root).resolve()
        git_path = root / ".git"
        if git_path.is_file():
            raw = git_path.read_text(encoding="utf-8").strip()
            if raw.startswith("gitdir:"):
                candidate = Path(raw[len("gitdir:") :].strip())
                if not candidate.is_absolute():
                    candidate = (root / candidate).resolve()
                git_path = candidate
        if git_path.exists():
            return cls(git_path / "harness-runs", **kwargs)
        # Unit-test fixtures and explicit non-Git dry-runs still need a local
        # state location, but must not create a fake .git directory.
        return cls(root / ".codex" / "run-state", **kwargs)

    def _path_for(self, task_id: str) -> Path:
        if not task_id:
            raise RunStateError("task_id는 비어 있을 수 없습니다")
        digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def begin(self, identity: RunIdentity) -> RunState:
        path = self._path_for(identity.task_id)
        if path.exists():
            state = self._read(path)
            if state.identity != identity:
                raise RunStateConflictError(
                    f"기존 run state의 identity가 현재 task와 다릅니다: {identity.task_id}"
                )
            return state
        now = self._clock()
        state = RunState(identity=identity, created_at=now, updated_at=now)
        self._write(path, state)
        return state

    def read(self, task_id: str) -> RunState:
        path = self._path_for(task_id)
        if not path.exists():
            raise RunStateError(f"run state를 찾지 못했습니다: {task_id}")
        return self._read(path)

    def transition(
        self,
        task_id: str,
        status: str,
        *,
        thread_id: str | None = None,
        process_id: int | None = None,
        verification_status: str | None = None,
        review_status: str | None = None,
        metrics: Mapping[str, object] | None = None,
        diagnostic: str | None = None,
        error: str | None = None,
    ) -> RunState:
        if status not in RUN_STATUSES:
            raise RunStateTransitionError(f"지원하지 않는 run status입니다: {status}")
        current = self.read(task_id)
        if status != current.status and status not in _TRANSITIONS[current.status]:
            raise RunStateTransitionError(f"허용되지 않는 상태 전이: {current.status} -> {status}")
        next_metrics = dict(current.metrics)
        if metrics is not None:
            unknown = set(metrics) - _METRIC_FIELDS
            if unknown:
                raise RunStateError(f"지원하지 않는 metrics 필드: {', '.join(sorted(unknown))}")
            next_metrics.update(_validated_metrics(metrics))
        diagnostics = current.diagnostics
        if diagnostic:
            sanitized = redact_text(diagnostic)
            if sanitized and sanitized not in diagnostics:
                diagnostics = (*diagnostics, sanitized)
        updated = replace(
            current,
            status=status,
            thread_id=current.thread_id if thread_id is None else _non_empty_or_none(thread_id, "thread_id"),
            process_id=current.process_id if process_id is None else _positive_or_none(process_id, "process_id"),
            verification_status=current.verification_status if verification_status is None else _check_gate_status(verification_status),
            review_status=current.review_status if review_status is None else _check_gate_status(review_status),
            metrics=next_metrics,
            diagnostics=diagnostics,
            last_error=current.last_error if error is None else redact_text(error),
            updated_at=self._clock(),
        )
        self._write(self._path_for(task_id), updated)
        return updated

    def resume(self, task_id: str, *, process_id: int | None = None) -> RunState:
        current = self.read(task_id)
        if current.status in TERMINAL_STATUSES:
            raise RunStateTransitionError(f"terminal run state는 재개할 수 없습니다: {task_id}")
        if current.status not in PRESERVED_STATUSES:
            raise RunStateTransitionError(f"중단된 run state만 재개할 수 있습니다: status={current.status}")
        resumed = replace(
            current,
            status="running",
            attempt=current.attempt + 1,
            process_id=os.getpid() if process_id is None else _positive_or_none(process_id, "process_id"),
            updated_at=self._clock(),
        )
        self._write(self._path_for(task_id), resumed)
        return resumed

    def complete_action(self, task_id: str, action: str, fingerprint: str) -> tuple[RunState, bool]:
        if not action or not fingerprint:
            raise RunStateError("action과 fingerprint는 비어 있을 수 없습니다")
        current = self.read(task_id)
        previous = current.completed_actions.get(action)
        if previous is not None:
            if previous != fingerprint:
                raise RunStateTransitionError(
                    f"완료 action의 fingerprint가 달라 중복 실행하지 않습니다: {action}"
                )
            return current, False
        actions = dict(current.completed_actions)
        actions[action] = fingerprint
        updated = replace(current, completed_actions=actions, updated_at=self._clock())
        self._write(self._path_for(task_id), updated)
        return updated, True

    def is_stale(self, task_id: str) -> bool:
        state = self.read(task_id)
        return state.process_id is not None and not self._process_exists(state.process_id)

    def _read(self, path: Path) -> RunState:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunStateCorruptionError(f"run state를 읽지 못했습니다: {path}: {exc}") from exc
        return _state_from_payload(payload, path)

    def _write(self, path: Path, state: RunState) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.to_payload(), ensure_ascii=False, indent=2) + "\n"
        descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temp_path = Path(raw_temp)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def _non_empty_or_none(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RunStateError(f"{name}은 non-empty string 또는 None이어야 합니다")
    return value


def _positive_or_none(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RunStateError(f"{name}은 양의 정수 또는 None이어야 합니다")
    return value


def _check_gate_status(value: object) -> str:
    if value not in {"pending", "passed", "failed", "not-applicable"}:
        raise RunStateError("verification/review status가 올바르지 않습니다")
    return str(value)


def _validated_metrics(metrics: Mapping[str, object]) -> dict[str, object]:
    validated: dict[str, object] = {}
    for key, value in metrics.items():
        if key in {"implementationRetryCount", "reviewFixCount", "humanInterventionCount"}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RunStateError(f"{key}는 0 이상의 정수여야 합니다")
        elif key == "wallTimeSeconds":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise RunStateError("wallTimeSeconds는 0 이상의 숫자여야 합니다")
        elif key == "tokens":
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise RunStateError("tokens는 0 이상의 정수 또는 None이어야 합니다")
        elif key == "unavailableReason":
            if value is not None and not isinstance(value, str):
                raise RunStateError("unavailableReason은 string 또는 None이어야 합니다")
            if isinstance(value, str):
                value = redact_text(value)
        validated[key] = value
    return validated


def _state_from_payload(payload: object, path: Path) -> RunState:
    if not isinstance(payload, dict):
        raise RunStateCorruptionError(f"run state가 JSON object가 아닙니다: {path}")
    if payload.get("schemaVersion") != RUN_STATE_SCHEMA_VERSION:
        raise RunStateCorruptionError(f"지원하지 않는 run state schemaVersion: {path}")

    def required_string(key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise RunStateCorruptionError(f"run state의 {key}가 올바르지 않습니다: {path}")
        return value

    try:
        worktree_path = Path(required_string("worktreePath"))
        identity = RunIdentity(
            phase=required_string("phase"),
            task_id=required_string("taskId"),
            issue=payload.get("issue"),
            branch=required_string("branch"),
            worktree_path=worktree_path,
            model=payload.get("model"),
            effort=payload.get("effort"),
        )
        status = required_string("status")
        if status not in RUN_STATUSES:
            raise RunStateCorruptionError(f"run state status가 올바르지 않습니다: {path}")
        attempt = payload.get("attempt")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
            raise RunStateCorruptionError(f"run state attempt가 올바르지 않습니다: {path}")
        metrics = payload.get("metrics", {})
        actions = payload.get("completedActions", {})
        diagnostics = payload.get("diagnostics", [])
        if not isinstance(metrics, dict) or not isinstance(actions, dict) or not isinstance(diagnostics, list):
            raise RunStateCorruptionError(f"run state collection 필드가 올바르지 않습니다: {path}")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in actions.items()):
            raise RunStateCorruptionError(f"run state completedActions가 올바르지 않습니다: {path}")
        if not all(isinstance(item, str) for item in diagnostics):
            raise RunStateCorruptionError(f"run state diagnostics가 올바르지 않습니다: {path}")
        return RunState(
            identity=identity,
            status=status,
            attempt=attempt,
            thread_id=_non_empty_or_none(payload.get("threadId"), "threadId"),
            process_id=_positive_or_none(payload.get("processId"), "processId"),
            verification_status=_check_gate_status(payload.get("verificationStatus")),
            review_status=_check_gate_status(payload.get("reviewStatus")),
            metrics=_validated_metrics(metrics),
            completed_actions=actions,
            diagnostics=tuple(diagnostics),
            last_error=_non_empty_or_none(payload.get("lastError"), "lastError"),
            created_at=required_string("createdAt"),
            updated_at=required_string("updatedAt"),
        )
    except RunStateError as exc:
        raise RunStateCorruptionError(f"run state가 올바르지 않습니다: {path}: {exc}") from exc
