#!/usr/bin/env python3
"""Probe the pinned Python Codex SDK without storing private thread content."""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.metadata
import inspect
import json
import platform
import re
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


SDK_DISTRIBUTION = "openai-codex"
RUNTIME_DISTRIBUTION = "openai-codex-cli-bin"
PINNED_SDK_VERSION = "0.147.0"
DEFAULT_MODEL = "gpt-5.6-terra"

_SENSITIVE_KEY_RE = re.compile(
    r"(?:credential|token|password|api[_-]?key|thread[_-]?id|response[_-]?(?:text|body)|prompt)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b(?:thread|thr)_[A-Za-z0-9_-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
    re.compile(r"/(?:Users|home)/[^/\s]+", re.IGNORECASE),
)


class SpikeError(RuntimeError):
    """Raised when the probe cannot produce a safe, comparable report."""


def _version(distribution: str) -> str:
    return importlib.metadata.version(distribution)


def require_pinned_version(actual: str) -> None:
    if actual != PINNED_SDK_VERSION:
        raise SpikeError(
            f"expected {SDK_DISTRIBUTION}=={PINNED_SDK_VERSION}, got {actual}"
        )


def classify_exception(exc: BaseException) -> dict[str, str]:
    """Return only a stable error class/category, never the exception message."""
    name = type(exc).__name__
    lowered = name.lower()
    if "auth" in lowered or "login" in lowered:
        category = "authentication"
    elif "timeout" in lowered:
        category = "timeout"
    elif "transport" in lowered or "closed" in lowered:
        category = "transport"
    elif "invalid" in lowered or "notfound" in lowered or "not_found" in lowered:
        category = "invalid-request"
    elif "retry" in lowered or "busy" in lowered or "overload" in lowered:
        category = "retryable-runtime"
    else:
        category = "runtime"
    return {"status": "failed", "category": category, "errorClass": name}


def _method_has_parameter(target: Callable[..., Any], parameter: str) -> bool:
    return parameter in inspect.signature(target).parameters


def static_capabilities(sdk: ModuleType) -> dict[str, Any]:
    codex = sdk.Codex
    thread = sdk.Thread
    turn_handle = sdk.TurnHandle
    config_signature = inspect.signature(sdk.CodexConfig)
    experimental_default = config_signature.parameters["experimental_api"].default
    return {
        "threadStart": hasattr(codex, "thread_start"),
        "threadRun": hasattr(thread, "run"),
        "threadResume": hasattr(codex, "thread_resume"),
        "threadPersistenceRead": hasattr(thread, "read"),
        "sandboxPresets": sorted(item.value for item in sdk.Sandbox),
        "approvalModes": sorted(item.value for item in sdk.ApprovalMode),
        "nativeTurnTimeoutParameter": _method_has_parameter(thread.run, "timeout"),
        "turnInterrupt": hasattr(turn_handle, "interrupt"),
        "modelList": hasattr(codex, "models"),
        "nativeReviewHighLevel": hasattr(codex, "review") or hasattr(thread, "review"),
        "appServerTransport": True,
        "experimentalApiDefault": experimental_default,
    }


def build_static_report() -> tuple[dict[str, Any], ModuleType]:
    sdk_version = _version(SDK_DISTRIBUTION)
    require_pinned_version(sdk_version)
    runtime_version = _version(RUNTIME_DISTRIBUTION)
    import openai_codex as sdk

    report = {
        "schemaVersion": 1,
        "package": {
            "sdk": f"{SDK_DISTRIBUTION}=={sdk_version}",
            "runtime": f"{RUNTIME_DISTRIBUTION}=={runtime_version}",
        },
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
        },
        "capabilities": static_capabilities(sdk),
        "privacy": {
            "credentialMaterialStored": False,
            "privateThreadIdentifierStored": False,
            "responseContentStored": False,
        },
        "live": {"status": "not-run", "reason": "pass --live to run authenticated probes"},
    }
    return report, sdk


def _timed(action: Callable[[], Any]) -> tuple[Any, float]:
    started = time.monotonic()
    value = action()
    return value, round(time.monotonic() - started, 3)


def _completed(result: Any) -> bool:
    return str(getattr(result, "status", "")).lower().endswith("completed")


def _run_text_turn(thread: Any, expected: str) -> tuple[bool, float]:
    result, elapsed = _timed(
        lambda: thread.run(f"Reply with exactly {expected} and do not use tools.")
    )
    return _completed(result) and result.final_response.strip() == expected, elapsed


def _probe_thread_lifecycle(sdk: ModuleType, cwd: str, model: str) -> dict[str, Any]:
    thread_identifier: str | None = None
    try:
        with sdk.Codex() as codex:
            account = codex.account()
            models = codex.models().data
            model_ids = {item.model for item in models}
            thread = codex.thread_start(
                cwd=cwd,
                model=model,
                sandbox=sdk.Sandbox.read_only,
                approval_mode=sdk.ApprovalMode.deny_all,
            )
            thread_identifier = thread.id
            started, start_seconds = _run_text_turn(thread, "SDK_START_OK")
            continued, continue_seconds = _run_text_turn(thread, "SDK_CONTINUE_OK")

        with sdk.Codex() as resumed_codex:
            resumed = resumed_codex.thread_resume(
                thread_identifier,
                cwd=cwd,
                model=model,
                sandbox=sdk.Sandbox.read_only,
                approval_mode=sdk.ApprovalMode.deny_all,
            )
            resumed_ok, resume_seconds = _run_text_turn(resumed, "SDK_RESUME_OK")
            same_identifier = resumed.id == thread_identifier
            resumed_codex.thread_archive(thread_identifier)

        return {
            "status": "passed",
            "authenticated": getattr(account, "account", None) is not None,
            "model": model,
            "modelAdvertised": model in model_ids,
            "modelCount": len(models),
            "start": started,
            "continue": continued,
            "resumeAfterClientRestart": resumed_ok and same_identifier,
            "wallTimeSeconds": {
                "start": start_seconds,
                "continue": continue_seconds,
                "resume": resume_seconds,
            },
        }
    except Exception as exc:  # the safe report intentionally omits raw messages
        return classify_exception(exc)


def _probe_sandbox_and_approval(sdk: ModuleType, cwd: str, model: str) -> dict[str, Any]:
    marker = Path(cwd) / "sandbox-marker.txt"
    try:
        with sdk.Codex() as codex:
            thread = codex.thread_start(
                cwd=cwd,
                model=model,
                sandbox=sdk.Sandbox.read_only,
                approval_mode=sdk.ApprovalMode.deny_all,
                ephemeral=True,
            )
            result = thread.run(
                "Use apply_patch to create sandbox-marker.txt containing "
                "SDK_SANDBOX_MARKER. Do not merely describe it."
            )
        return {
            "status": "passed" if not marker.exists() else "failed",
            "turnReachedTerminalState": str(getattr(result, "status", ""))
            .lower()
            .endswith(("completed", "failed", "interrupted")),
            "readOnlyWriteBlocked": not marker.exists(),
            "approvalMode": "deny_all",
            "humanInterventionCount": 0,
        }
    except Exception as exc:
        return classify_exception(exc)


def _probe_error_recovery(sdk: ModuleType, cwd: str, model: str) -> dict[str, Any]:
    intentional_error: dict[str, str] | None = None
    recovered = False
    try:
        with sdk.Codex() as codex:
            try:
                codex.thread_resume(
                    "00000000-0000-0000-0000-000000000000",
                    cwd=cwd,
                    sandbox=sdk.Sandbox.read_only,
                    approval_mode=sdk.ApprovalMode.deny_all,
                )
            except Exception as exc:
                intentional_error = classify_exception(exc)
            thread = codex.thread_start(
                cwd=cwd,
                model=model,
                sandbox=sdk.Sandbox.read_only,
                approval_mode=sdk.ApprovalMode.deny_all,
                ephemeral=True,
            )
            recovered, _ = _run_text_turn(thread, "SDK_RECOVERY_OK")
        return {
            "status": "passed" if intentional_error and recovered else "failed",
            "intentionalFailure": intentional_error,
            "sameClientRecovered": recovered,
        }
    except Exception as exc:
        return classify_exception(exc)


def _probe_timeout_and_interrupt(
    sdk: ModuleType,
    cwd: str,
    model: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    command = "Start-Sleep -Seconds 30" if sys.platform == "win32" else "sleep 30"
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    codex = None
    timed_out = False
    interrupted = False
    terminal = "unknown"
    try:
        codex = sdk.Codex()
        thread = codex.thread_start(
            cwd=cwd,
            model=model,
            sandbox=sdk.Sandbox.read_only,
            approval_mode=sdk.ApprovalMode.auto_review,
            ephemeral=True,
        )
        handle = thread.turn(
            f"Run this exact shell command before replying: {command}. Then reply DONE."
        )
        future = executor.submit(handle.run)
        try:
            future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            timed_out = True
            handle.interrupt()
            interrupted = True
        result = future.result(timeout=30)
        terminal = str(getattr(result, "status", "unknown"))
        passed = timed_out and interrupted and terminal.lower().endswith("interrupted")
        return {
            "status": "passed" if passed else "failed",
            "sdkNativeTimeoutParameter": False,
            "callerTimeoutTriggered": timed_out,
            "interruptSent": interrupted,
            "terminalStatus": terminal.split(".")[-1].lower(),
        }
    except Exception as exc:
        return classify_exception(exc)
    finally:
        executor.shutdown(wait=True)
        if codex is not None:
            codex.close()


def run_live_probes(
    report: dict[str, Any],
    sdk: ModuleType,
    *,
    model: str,
    timeout_seconds: float,
) -> None:
    with tempfile.TemporaryDirectory(prefix="codex-sdk-spike-") as cwd:
        report["live"] = {
            "status": "completed",
            "threadLifecycle": _probe_thread_lifecycle(sdk, cwd, model),
            "sandboxAndApproval": _probe_sandbox_and_approval(sdk, cwd, model),
            "errorRecovery": _probe_error_recovery(sdk, cwd, model),
            "timeoutAndInterrupt": _probe_timeout_and_interrupt(
                sdk, cwd, model, timeout_seconds
            ),
        }


def assert_safe_report(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)) and child not in (False, None):
                raise SpikeError(f"unsafe report key at {path}.{key}")
            assert_safe_report(child, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            assert_safe_report(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in _SENSITIVE_VALUE_RES):
            raise SpikeError(f"unsafe report value at {path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Run authenticated live probes")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model used by live probes")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=1.0,
        help="Caller timeout before interrupting the long-running probe turn",
    )
    parser.add_argument("--output", type=Path, help="Write the sanitized JSON report")
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report, sdk = build_static_report()
        if args.live:
            run_live_probes(
                report,
                sdk,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
            )
        assert_safe_report(report)
    except (SpikeError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1

    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
