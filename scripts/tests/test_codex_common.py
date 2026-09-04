from pathlib import Path
import tomllib

import pytest

import codex_common


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
