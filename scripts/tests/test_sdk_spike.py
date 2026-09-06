import json
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

import sdk_spike


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
