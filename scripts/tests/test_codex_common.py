from pathlib import Path
import tomllib

import pytest

import codex_common
import codex_runner


def test_validate_codex_effort_rejects_xhigh_without_flag():
    with pytest.raises(ValueError, match="xhigh"):
        codex_common.validate_codex_effort("xhigh")

    assert codex_common.validate_codex_effort("xhigh", allow_xhigh=True) == "xhigh"


def test_validate_codex_effort_rejects_unknown_value():
    with pytest.raises(ValueError, match="minimal"):
        codex_common.validate_codex_effort("extreme")


def test_codex_base_cmd_uses_stdin_compatible_exec_shape():
    cmd = codex_common.codex_base_cmd("medium")

    assert cmd[1] == "exec"
    assert "--json" in cmd
    assert 'model_reasoning_effort="medium"' in cmd
    assert codex_common.CODEX_ENV_CONFIG in cmd
    assert codex_common.CODEX_ENV_SECRET_FILTER_CONFIG in cmd
    assert "shell_environment_policy.inherit=all" not in cmd
    assert "shell_environment_policy.include_only" not in cmd
    assert "shell_environment_policy.exclude" not in cmd


def test_codex_project_config_declares_minimal_policy_and_extension_point():
    config_path = Path(__file__).resolve().parents[2] / ".codex" / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    policy = config["shell_environment_policy"]
    assert policy["inherit"] == "core"
    assert policy["ignore_default_excludes"] is False
    assert isinstance(policy["filters"], dict)


def test_codex_command_enables_default_secret_name_exclusion_without_values():
    secret_name_fixture = {
        "PROJECT_RUNTIME_HOME": "runtime-sentinel",
        "PAYMENT_API_TOKEN": "secret-name-only",
        "AWS_SECRET_ACCESS_KEY": "secret-name-only",
    }
    cmd = codex_common.codex_base_cmd("medium")

    assert codex_common.CODEX_ENV_SECRET_FILTER_CONFIG in cmd
    assert all(name not in cmd and value not in cmd for name, value in secret_name_fixture.items())


@pytest.mark.parametrize(
    ("platform", "expected_candidates"),
    [
        ("win32", ("codex.cmd", "codex.exe", "codex")),
        ("darwin", ("codex",)),
        ("linux", ("codex",)),
    ],
)
def test_resolve_codex_bin_preserves_platform_runtime_lookup(monkeypatch, platform, expected_candidates):
    calls = []

    def fake_which(candidate):
        calls.append(candidate)
        return f"/runtime/{candidate}" if candidate == expected_candidates[-1] else None

    monkeypatch.setattr(codex_common.sys, "platform", platform)
    monkeypatch.setattr(codex_common.shutil, "which", fake_which)

    assert codex_common.resolve_codex_bin() == f"/runtime/{expected_candidates[-1]}"
    assert calls == list(expected_candidates)


def test_read_acceptance_commands_extracts_fenced_commands(tmp_path):
    step = tmp_path / "step0.md"
    step.write_text(
        "\n".join(
            [
                "# 단계 0",
                "",
                "## 인수 기준",
                "",
                "```bash",
                "# comment",
                "python -m pytest",
                "python -m compileall scripts",
                "```",
                "",
                "## 다음 섹션",
                "```bash",
                "echo ignored",
                "```",
            ]
        ),
        encoding="utf-8",
    )

    assert codex_common.read_acceptance_commands(step) == (
        "python -m pytest",
        "python -m compileall scripts",
    )


def test_configure_utf8_stdio_is_safe_to_call():
    codex_common.configure_utf8_stdio()


def test_runner_uses_exec_by_default_and_sdk_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("HARNESS_CODEX_RUNNER", raising=False)
    assert codex_runner.runner_preference() == "exec"

    monkeypatch.setenv("HARNESS_CODEX_RUNNER", "sdk")
    assert codex_runner.runner_preference() == "sdk"


def test_runner_rejects_unknown_preference_fail_closed(monkeypatch):
    monkeypatch.setenv("HARNESS_CODEX_RUNNER", "unknown")
    with pytest.raises(codex_runner.RunnerCapabilityError, match="HARNESS_CODEX_RUNNER"):
        codex_runner.runner_preference()


def test_exec_adapter_normalizes_thread_id_without_exposing_it_in_result():
    completed = __import__("subprocess").CompletedProcess(
        ["codex"], 0, '{"thread_id":"thread-secret","type":"turn.completed"}\n', ""
    )
    runner = codex_runner.ExecRunner(run_process=lambda *args, **kwargs: completed)

    result = runner.run(codex_runner.RunnerSession("exec"), codex_runner.RunnerRequest(prompt="test"))

    assert result.ok is True
    assert result.thread_id == "thread-secret"
    assert "thread-secret" not in result.to_record()


def test_exec_adapter_resume_uses_session_id_and_preserves_stdin_safety():
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs["input"]
        return __import__("subprocess").CompletedProcess(cmd, 0, "", "")

    runner = codex_runner.ExecRunner(run_process=fake_run)
    runner.resume(codex_runner.RunnerSession("exec", "safe-session"), codex_runner.RunnerRequest(prompt="continue"))

    assert seen["cmd"][1:3] == ["exec", "resume"]
    assert "safe-session" in seen["cmd"]
    assert seen["cmd"][-1] == "-"
    assert seen["input"] == "continue"


def test_sdk_capability_failure_falls_back_once_to_exec():
    fallback = []

    class BrokenSdk:
        name = "sdk"

        def start(self, request):
            raise codex_runner.RunnerCapabilityError("pinned runtime mismatch")

    class Exec:
        name = "exec"

        def start(self, request):
            fallback.append(request)
            return codex_runner.RunnerResult.success("exec", fallback_reason="pinned runtime mismatch")

    result = codex_runner.FallbackRunner(BrokenSdk(), Exec()).start(codex_runner.RunnerRequest(prompt="safe"))
    assert result.ok is True
    assert result.adapter == "exec"
    assert result.fallback_reason == "pinned runtime mismatch"
    assert len(fallback) == 1


def test_nonrecoverable_sdk_error_does_not_fallback():
    class BrokenSdk:
        name = "sdk"

        def start(self, request):
            raise codex_runner.RunnerExecutionError("approval denied", recoverable=False)

    class Exec:
        name = "exec"

        def start(self, request):
            raise AssertionError("non-recoverable errors must not retry through exec")

    with pytest.raises(codex_runner.RunnerExecutionError, match="approval denied"):
        codex_runner.FallbackRunner(BrokenSdk(), Exec()).start(codex_runner.RunnerRequest(prompt="safe"))


def test_executor_and_autopilot_do_not_assemble_codex_argv_directly():
    root = Path(__file__).resolve().parents[2]
    for path in (root / "scripts" / "execute.py", root / "scripts" / "autopilot.py"):
        source = path.read_text(encoding="utf-8")
        assert "codex_base_cmd" not in source
        assert "resolve_codex_bin" not in source


def test_sdk_timeout_is_fail_closed_after_bounded_cleanup():
    class Thread:
        id = "ephemeral-thread"

        def run(self, prompt):
            __import__("time").sleep(0.05)

        def interrupt(self):
            return None

    runner = codex_runner.SdkRunner.__new__(codex_runner.SdkRunner)
    runner._codex = type("Client", (), {"close": lambda self: None})()
    result = runner._run_thread(Thread(), codex_runner.RunnerRequest(prompt="slow", timeout=0))

    assert result.ok is False
    assert result.exit_code == 124
    assert result.error_kind == "timeout"


def test_sdk_explicit_interrupt_is_bounded_and_fail_closed():
    runner = codex_runner.SdkRunner.__new__(codex_runner.SdkRunner)
    runner._threads = {"thread": type("Thread", (), {"interrupt": lambda self: None})()}
    runner._bounded_call = lambda callback: False

    result = runner.interrupt(codex_runner.RunnerSession("sdk", "thread"))

    assert result.ok is False
    assert result.error_kind == "interrupt_timeout"
