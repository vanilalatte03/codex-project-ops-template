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
