import json
import threading
import time
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

import sdk_spike


def test_runtime_version_mismatch_fails_before_sdk_import(monkeypatch):
    monkeypatch.setattr(sdk_spike, "_version", lambda name:
                        "0.148.0" if name == sdk_spike.RUNTIME_DISTRIBUTION else "0.147.0")
    with pytest.raises(sdk_spike.SpikeError, match="openai-codex-cli-bin"):
        sdk_spike.build_static_report()


@pytest.mark.parametrize("failed", [None, "auth", "model", "start", "continue", "resume", "identity"])
def test_lifecycle_requires_every_check(monkeypatch, failed):
    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def account(self):
            return SimpleNamespace(account=None if failed == "auth" else object())

        def models(self):
            return SimpleNamespace(data=[] if failed == "model" else [SimpleNamespace(model="test")])

        def thread_start(self, **kwargs):
            return SimpleNamespace(id="fixture")

        def thread_resume(self, *args, **kwargs):
            return SimpleNamespace(id="different" if failed == "identity" else "fixture")

        def thread_archive(self, *args):
            pass

    outcomes = iter([(failed != key, 0.0) for key in ("start", "continue", "resume")])
    monkeypatch.setattr(sdk_spike, "_run_text_turn", lambda *args: next(outcomes))
    sdk = SimpleNamespace(Codex=Client, Sandbox=SimpleNamespace(read_only="read-only"),
                          ApprovalMode=SimpleNamespace(deny_all="deny_all"))
    result = sdk_spike._probe_thread_lifecycle(sdk, ".", "test")
    assert result["status"] == ("passed" if failed is None else "failed")


@pytest.mark.parametrize("failure", ["interrupt", "terminal", "close", None])
def test_timeout_cleanup_is_bounded_and_fail_closed(monkeypatch, failure):
    released = threading.Event()
    closed = threading.Event()
    monkeypatch.setattr(sdk_spike, "TERMINAL_WAIT_SECONDS", 0.03)
    monkeypatch.setattr(sdk_spike, "CLEANUP_WAIT_SECONDS", 0.03)

    class Handle:
        def run(self):
            released.wait(2)
            return SimpleNamespace(status="interrupted")

        def interrupt(self):
            if failure == "interrupt":
                raise RuntimeError("private message")
            if failure not in ("terminal", "close"):
                released.set()

    class Client:
        def thread_start(self, **kwargs):
            return SimpleNamespace(turn=lambda *args: Handle())

        def close(self):
            closed.set()
            if failure == "close":
                released.wait(2)
            else:
                released.set()

    sdk = SimpleNamespace(Codex=Client, Sandbox=SimpleNamespace(read_only="read-only"),
                          ApprovalMode=SimpleNamespace(auto_review="auto_review"))
    started = time.monotonic()
    try:
        result = sdk_spike._probe_timeout_and_interrupt(sdk, ".", "test", 0.01)
        assert time.monotonic() - started < 1
        assert closed.is_set()
        assert result["status"] == ("passed" if failure is None else "failed")
        sdk_spike.assert_safe_report(result)
    finally:
        released.set()


def test_require_pinned_version_rejects_drift():
    with pytest.raises(sdk_spike.SpikeError, match="expected openai-codex==0.147.0"):
        sdk_spike.require_pinned_version("0.148.0")


def test_classify_exception_does_not_store_message():
    failure = sdk_spike.classify_exception(
        RuntimeError("sk-secret-value thread_private C:\\Users\\private")
    )

    assert failure == {
        "status": "failed",
        "category": "runtime",
        "errorClass": "RuntimeError",
    }


def test_static_capabilities_separates_timeout_interrupt_and_native_review():
    class Approval(Enum):
        deny_all = "deny_all"
        auto_review = "auto_review"

    class Sandbox(Enum):
        read_only = "read-only"
        workspace_write = "workspace-write"

    class CodexConfig:
        def __init__(self, experimental_api: bool = True):
            pass

    class Codex:
        def thread_start(self):
            pass

        def thread_resume(self):
            pass

        def models(self):
            pass

    class Thread:
        def run(self):
            pass

        def read(self):
            pass

    class TurnHandle:
        def interrupt(self):
            pass

    sdk = SimpleNamespace(
        ApprovalMode=Approval,
        Sandbox=Sandbox,
        CodexConfig=CodexConfig,
        Codex=Codex,
        Thread=Thread,
        TurnHandle=TurnHandle,
    )

    capabilities = sdk_spike.static_capabilities(sdk)

    assert capabilities["threadStart"] is True
    assert capabilities["threadResume"] is True
    assert capabilities["nativeTurnTimeoutParameter"] is False
    assert capabilities["turnInterrupt"] is True
    assert capabilities["nativeReviewHighLevel"] is False
    assert capabilities["experimentalApiDefault"] is True


@pytest.mark.parametrize(
    "unsafe",
    [
        {"threadId": "private"},
        {"prompt": "harmless-looking"},
        {"value": "sk-secret-value"},
        {"value": "C:\\Users\\private\\file.txt"},
    ],
)
def test_assert_safe_report_rejects_sensitive_keys_and_values(unsafe):
    with pytest.raises(sdk_spike.SpikeError, match="unsafe report"):
        sdk_spike.assert_safe_report(unsafe)


def test_assert_safe_report_accepts_boolean_privacy_attestations():
    sdk_spike.assert_safe_report(
        {
            "credentialMaterialStored": False,
            "privateThreadIdentifierStored": False,
            "responseContentStored": False,
        }
    )


def test_parse_args_defaults_to_offline_probe():
    args = sdk_spike.parse_args([])

    assert args.live is False
    assert args.model == "gpt-5.6-terra"
    assert args.timeout_seconds == 1.0


def test_committed_result_is_sanitized_and_matches_pin():
    result_path = (
        Path(__file__).resolve().parents[2]
        / "phases"
        / "harness-v2-modernization"
        / "SDK_SPIKE_RESULTS.json"
    )
    report = json.loads(result_path.read_text(encoding="utf-8"))

    sdk_spike.assert_safe_report(report)
    assert report["package"]["sdk"] == "openai-codex==0.147.0"
    assert report["package"]["runtime"] == "openai-codex-cli-bin==0.147.0"
    assert report["live"]["threadLifecycle"]["resumeAfterClientRestart"] is True
    assert report["live"]["timeoutAndInterrupt"]["terminalStatus"] == "interrupted"


def test_main_redacts_unexpected_error_message(monkeypatch, capsys):
    def fail():
        raise RuntimeError("sk-secret-value C:\\Users\\private")

    monkeypatch.setattr(sdk_spike, "build_static_report", fail)

    assert sdk_spike.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: RuntimeError\n"
