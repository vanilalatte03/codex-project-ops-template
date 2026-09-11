"""Stable runner boundary for Codex CLI and the optional Python SDK.

This module is the only Harness layer that knows Codex argv or SDK call shapes.
It deliberately exposes a small, sanitized result surface: callers may keep a
thread id in memory for resume, but must not persist it in phase artifacts.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Protocol

from codex_common import CODEX_EXEC_TIMEOUT, codex_base_cmd

SDK_PACKAGE = "openai-codex"
SDK_PIN = "0.147.0"


class RunnerError(RuntimeError):
    recoverable = False


class RunnerCapabilityError(RunnerError):
    recoverable = True


class RunnerExecutionError(RunnerError):
    def __init__(self, message: str, *, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable


@dataclass(frozen=True)
class RunnerRequest:
    prompt: str
    mode: str = "run"
    effort: str = "medium"
    sandbox: str | None = None
    timeout: int | None = CODEX_EXEC_TIMEOUT
    unsafe: bool = False
    output_schema: str | None = None
    output_last_message: str | None = None


@dataclass(frozen=True)
class RunnerSession:
    adapter: str
    thread_id: str | None = None


@dataclass(frozen=True)
class RunnerResult:
    ok: bool
    adapter: str
    exit_code: int = 0
    final_message: str = ""
    thread_id: str | None = None
    error_kind: str | None = None
    fallback_reason: str | None = None

    @classmethod
    def success(cls, adapter: str, **kwargs) -> "RunnerResult":
        return cls(True, adapter, **kwargs)

    def to_record(self) -> dict:
        """Return a commit-safe record; never include thread/prompt/raw output."""
        return {
            "ok": self.ok,
            "adapter": self.adapter,
            "exitCode": self.exit_code,
            "errorKind": self.error_kind,
            "fallbackReason": self.fallback_reason,
        }


class RunnerAdapter(Protocol):
    name: str
    def start(self, request: RunnerRequest) -> RunnerResult: ...
    def run(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult: ...
    def resume(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult: ...
    def review(self, session: RunnerSession | None, request: RunnerRequest) -> RunnerResult: ...
    def interrupt(self, session: RunnerSession) -> RunnerResult: ...
    def close(self) -> None: ...


def runner_preference() -> str:
    preference = os.environ.get("HARNESS_CODEX_RUNNER", "exec").strip().lower() or "exec"
    if preference not in {"exec", "sdk"}:
        raise RunnerCapabilityError("HARNESS_CODEX_RUNNER must be 'exec' or explicit opt-in 'sdk'")
    return preference


def _thread_id(stdout: str) -> str | None:
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        for key in ("thread_id", "threadId", "session_id", "sessionId"):
            value = event.get(key)
            if isinstance(value, str) and value:
                return value
    return None


class ExecRunner:
    name = "exec"

    def __init__(self, *, run_process: Callable[..., subprocess.CompletedProcess] | None = None):
        # Resolve at construction so unit-test monkeypatches and runtime wrappers apply.
        self._run_process = run_process or subprocess.run

    def _command(self, request: RunnerRequest, *, resume: str | None = None) -> list[str]:
        cmd = codex_base_cmd(request.effort)
        if resume:
            cmd = [cmd[0], "exec", "resume", resume, *cmd[2:]]
        if request.sandbox:
            cmd.extend(["--sandbox", request.sandbox])
        if request.unsafe:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        if request.output_schema:
            cmd.extend(["--output-schema", request.output_schema])
        if request.output_last_message:
            cmd.extend(["--output-last-message", request.output_last_message])
        cmd.append("-")
        return cmd

    def _invoke(self, request: RunnerRequest, *, resume: str | None = None) -> RunnerResult:
        cmd = self._command(request, resume=resume)
        try:
            completed = self._run_process(
                cmd, input=request.prompt, capture_output=True, text=True, timeout=request.timeout
            )
        except subprocess.TimeoutExpired as exc:
            return RunnerResult(False, self.name, 124, error_kind="timeout")
        except OSError as exc:
            raise RunnerExecutionError("codex exec could not start", recoverable=True) from exc
        message = ""
        if request.output_last_message:
            try:
                with open(request.output_last_message, encoding="utf-8") as file:
                    message = file.read()
            except OSError:
                pass
        if not message:
            message = completed.stdout or ""
        if completed.returncode:
            return RunnerResult(False, self.name, completed.returncode, error_kind="exec_failed")
        return RunnerResult.success(self.name, final_message=message, thread_id=_thread_id(completed.stdout or ""))

    def start(self, request: RunnerRequest) -> RunnerResult:
        return self._invoke(request)

    def run(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult:
        return self.resume(session, request) if session.thread_id else self.start(request)

    def resume(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult:
        if not session.thread_id:
            raise RunnerCapabilityError("resume requires an in-memory runner session")
        return self._invoke(request, resume=session.thread_id)

    def review(self, session: RunnerSession | None, request: RunnerRequest) -> RunnerResult:
        return self.run(session, request) if session else self.start(request)

    def interrupt(self, session: RunnerSession) -> RunnerResult:
        return RunnerResult(False, self.name, error_kind="interrupt_unsupported")

    def close(self) -> None:
        return None


class SdkRunner:
    """Best-effort SDK adapter, selected only by explicit feature flag."""
    name = "sdk"

    def __init__(self):
        try:
            installed = importlib.metadata.version(SDK_PACKAGE)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RunnerCapabilityError("Python Codex SDK is not installed") from exc
        if installed != SDK_PIN:
            raise RunnerCapabilityError("Python Codex SDK/runtime pin does not match ADR-0005")
        try:
            from openai_codex import Codex, Sandbox  # type: ignore
        except ImportError as exc:
            raise RunnerCapabilityError("Python Codex SDK import failed") from exc
        self._codex = Codex()
        self._sandbox = Sandbox
        self._threads: dict[str, object] = {}

    def _run_thread(self, thread: object, request: RunnerRequest) -> RunnerResult:
        # The pinned SDK has no cancellable caller-deadline primitive.  Running it
        # in a daemon thread would let an uninterruptible turn keep modifying the
        # worktree after Harness reports a timeout, so route deadline-bound work to
        # the recoverable exec fallback instead.
        if request.timeout is not None:
            raise RunnerCapabilityError("SDK bounded timeout is unavailable; use exec fallback")
        try:
            result = thread.run(request.prompt)
        except BaseException as exc:  # SDK typed errors vary across pinned runtime surfaces.
            raise RunnerExecutionError("SDK run failed", recoverable=True) from exc
        thread_id = getattr(thread, "id", None) or getattr(thread, "thread_id", None)
        return RunnerResult.success(self.name, final_message=str(getattr(result, "final_response", "")), thread_id=thread_id)

    @staticmethod
    def _bounded_call(callback: object, timeout: float = 5.0) -> bool:
        if not callable(callback):
            return False
        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(timeout)
        return not worker.is_alive()

    def start(self, request: RunnerRequest) -> RunnerResult:
        sandbox = getattr(self._sandbox, "workspace_write") if request.sandbox != "read-only" else getattr(self._sandbox, "read_only")
        try:
            thread = self._codex.thread_start(sandbox=sandbox)
        except Exception as exc:
            raise RunnerExecutionError("SDK thread start failed", recoverable=True) from exc
        result = self._run_thread(thread, request)
        if result.thread_id:
            self._threads[result.thread_id] = thread
        return result

    def run(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult:
        return self.resume(session, request) if session.thread_id else self.start(request)

    def resume(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult:
        if not session.thread_id:
            raise RunnerCapabilityError("resume requires an in-memory runner session")
        thread = self._threads.get(session.thread_id)
        if thread is None:
            try:
                thread = self._codex.thread_resume(session.thread_id)
            except Exception as exc:
                raise RunnerExecutionError("SDK resume failed", recoverable=True) from exc
        return self._run_thread(thread, request)

    def review(self, session: RunnerSession | None, request: RunnerRequest) -> RunnerResult:
        # ADR-0005: native review remains out of scope; run the read-only turn.
        return self.run(session, request) if session else self.start(request)

    def interrupt(self, session: RunnerSession) -> RunnerResult:
        thread = self._threads.get(session.thread_id or "")
        try:
            interrupt = getattr(thread, "interrupt", None)
            if not callable(interrupt):
                return RunnerResult(False, self.name, error_kind="interrupt_unsupported")
            if not self._bounded_call(interrupt):
                return RunnerResult(False, self.name, error_kind="interrupt_timeout")
            return RunnerResult.success(self.name)
        except Exception:
            return RunnerResult(False, self.name, error_kind="interrupt_failed")

    def close(self) -> None:
        self._bounded_call(getattr(self._codex, "close", None))


class FallbackRunner:
    """Fallback only for recoverable SDK capability/execution failures."""
    def __init__(self, primary: RunnerAdapter, fallback: RunnerAdapter):
        self.primary, self.fallback, self.name = primary, fallback, primary.name

    def _call(self, method: str, *args) -> RunnerResult:
        try:
            return getattr(self.primary, method)(*args)
        except RunnerError as exc:
            if not exc.recoverable:
                raise
            result = getattr(self.fallback, method)(*args)
            return RunnerResult(
                result.ok, result.adapter, result.exit_code, result.final_message, result.thread_id,
                result.error_kind, fallback_reason=str(exc),
            )

    def start(self, request: RunnerRequest) -> RunnerResult: return self._call("start", request)
    def run(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult: return self._call("run", session, request)
    def resume(self, session: RunnerSession, request: RunnerRequest) -> RunnerResult: return self._call("resume", session, request)
    def review(self, session: RunnerSession | None, request: RunnerRequest) -> RunnerResult: return self._call("review", session, request)
    def interrupt(self, session: RunnerSession) -> RunnerResult: return self._call("interrupt", session)
    def close(self) -> None:
        self.primary.close()
        self.fallback.close()


def build_runner(*, process_runner: Callable[..., subprocess.CompletedProcess] | None = None) -> RunnerAdapter:
    exec_runner = ExecRunner(run_process=process_runner)
    if runner_preference() == "exec":
        return exec_runner
    try:
        return FallbackRunner(SdkRunner(), exec_runner)
    except RunnerCapabilityError as exc:
        # Selecting SDK remains explicit, but a missing/incompatible optional SDK is safe to fall back.
        return FallbackRunner(_UnavailableSdk(exc), exec_runner)


class _UnavailableSdk:
    name = "sdk"
    def __init__(self, error: RunnerCapabilityError): self.error = error
    def start(self, request): raise self.error
    def run(self, session, request): raise self.error
    def resume(self, session, request): raise self.error
    def review(self, session, request): raise self.error
    def interrupt(self, session): raise self.error
    def close(self): return None
