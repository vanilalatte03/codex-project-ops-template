import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import checks


def test_commands_from_docs_reads_active_table(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "COMMANDS.md").write_text(
        """
## 활성 명령

| 이름 | 명령 | 필수 | 설명 |
| --- | --- | --- | --- |
| lint | `ruff check .` | no | lint |
| test | `python -m pytest` | yes | tests |
| build |  | yes | empty |
""".strip()
    )

    result = checks.commands_from_docs(tmp_path)

    assert result["lint"][0].command == "ruff check ."
    assert result["test"][0].command == "python -m pytest"
    assert "build" not in result


def test_profile_commands_take_precedence(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "project-profile.json").write_text(
        json.dumps({"commands": {"test": ["custom test"]}})
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "COMMANDS.md").write_text(
        """
## 활성 명령
| 이름 | 명령 | 필수 | 설명 |
| --- | --- | --- | --- |
| test | `docs test` | yes | tests |
""".strip()
    )

    selected = checks.collect_checks(tmp_path)

    assert [command.command for command in selected] == ["custom test"]


def test_collect_checks_falls_back_per_missing_command(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "project-profile.json").write_text(
        json.dumps({"commands": {"test": ["custom test"]}})
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "COMMANDS.md").write_text(
        """
## 활성 명령
| 이름 | 명령 | 필수 | 설명 |
| --- | --- | --- | --- |
| test | `docs test` | yes | tests |
| build | `docs build` | yes | build |
""".strip()
    )

    selected = checks.collect_checks(tmp_path)

    assert [command.command for command in selected] == ["custom test", "docs build"]


def test_detect_node_uses_lockfile_package_manager(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest", "build": "vite build"}}))
    (tmp_path / "pnpm-lock.yaml").write_text("")

    selected = checks.detect_commands(tmp_path)

    assert selected["test"][0].command == "pnpm test"
    assert selected["build"][0].command == "pnpm build"


def test_detect_spring_prefers_gradle(tmp_path):
    (tmp_path / "gradlew").write_text("")
    (tmp_path / "pom.xml").write_text("<project />")

    with patch.object(checks.sys, "platform", "linux"):
        selected = checks.detect_commands(tmp_path)

    assert selected["test"][0].command == "./gradlew test"
    assert selected["build"][0].command == "./gradlew build"


def test_detect_spring_uses_windows_gradle_wrapper(tmp_path):
    (tmp_path / "gradlew.bat").write_text("")
    (tmp_path / "build.gradle").write_text("")

    with patch.object(checks.sys, "platform", "win32"):
        selected = checks.detect_commands(tmp_path)

    assert selected["test"][0].command == ".\\gradlew.bat test"
    assert selected["build"][0].command == ".\\gradlew.bat build"


def test_detect_spring_uses_windows_maven_wrapper(tmp_path):
    (tmp_path / "mvnw.cmd").write_text("")
    (tmp_path / "pom.xml").write_text("<project />")

    with patch.object(checks.sys, "platform", "win32"):
        selected = checks.detect_commands(tmp_path)

    assert selected["test"][0].command == ".\\mvnw.cmd test"
    assert selected["build"][0].command == ".\\mvnw.cmd package"


def test_detect_python_uses_uv_when_available(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    with patch("shutil.which", return_value="/opt/bin/uv"):
        selected = checks.detect_commands(tmp_path)

    assert selected["test"][0].command == "uv run pytest"
    assert selected["lint"][0].command == "uv run ruff check ."


def test_placeholder_commands_are_ignored():
    assert not checks.is_real_command("<docs/COMMANDS.md의 test 명령>")
    assert not checks.is_real_command("")
    assert checks.is_real_command("python -m pytest")


def test_run_checks_fails_when_required_commands_are_missing(capsys):
    status = checks.run_checks([], Path.cwd())

    captured = capsys.readouterr()
    assert status == 1
    assert "Missing required check commands: test, build" in captured.err


def test_run_checks_executes_when_required_commands_exist(tmp_path):
    commands = [
        checks.CheckCommand("test", "python3 -c 'print(\"test ok\")'", "test"),
        checks.CheckCommand("build", "python3 -c 'print(\"build ok\")'", "test"),
    ]

    status = checks.run_checks(commands, tmp_path)

    assert status == 0


def test_stop_stage_defaults_to_lint_only(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "project-profile.json").write_text(
        json.dumps({"commands": {"lint": ["custom lint"], "test": ["custom test"], "build": ["custom build"]}})
    )

    stop_selected = checks.collect_checks(tmp_path, "stop")
    manual_selected = checks.collect_checks(tmp_path, "manual")

    assert [command.name for command in stop_selected] == ["lint"]
    assert [command.name for command in manual_selected] == ["lint", "test", "build"]


def test_stage_checks_profile_override_expands_stop_stage(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "project-profile.json").write_text(
        json.dumps(
            {
                "commands": {"lint": ["custom lint"], "test": ["custom test"]},
                "stageChecks": {"stop": ["lint", "test"]},
            }
        )
    )

    stop_selected = checks.collect_checks(tmp_path, "stop")

    assert [command.name for command in stop_selected] == ["lint", "test"]


def test_run_checks_timeout_returns_124(tmp_path, capsys):
    commands = [
        checks.CheckCommand("test", "slow test", "test"),
        checks.CheckCommand("build", "slow build", "test"),
    ]

    with patch("subprocess.run", side_effect=checks.subprocess.TimeoutExpired(cmd="slow", timeout=1)):
        status = checks.run_checks(commands, tmp_path, timeout=1)

    assert status == 124
    assert "timed out" in capsys.readouterr().err


def test_run_checks_streams_without_capture(tmp_path):
    commands = [
        checks.CheckCommand("test", "echo test", "test"),
        checks.CheckCommand("build", "echo build", "test"),
    ]

    with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
        status = checks.run_checks(commands, tmp_path, timeout=123)

    assert status == 0
    assert mock_run.call_args.kwargs["timeout"] == 123
    assert "capture_output" not in mock_run.call_args.kwargs


def test_docs_check_required_forbidden_and_final_rules(tmp_path, capsys):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PRD.md").write_text("READY\nDO_NOT_SHIP\n", encoding="utf-8")
    config = tmp_path / "docs-checks.json"
    config.write_text(
        json.dumps(
            {
                "paths": ["docs"],
                "required": [{"name": "ready marker", "pattern": "READY"}],
                "finalRequired": [{"name": "qa marker", "pattern": "QA_PASS"}],
                "forbidden": [{"name": "forbidden marker", "pattern": "DO_NOT_SHIP"}],
            }
        ),
        encoding="utf-8",
    )

    assert checks.run_docs_checks(tmp_path, str(config)) == 1
    captured = capsys.readouterr()
    assert "Forbidden docs marker" in captured.err

    (docs / "PRD.md").write_text("READY\n", encoding="utf-8")
    assert checks.run_docs_checks(tmp_path, str(config)) == 0
    assert checks.run_docs_checks(tmp_path, str(config), include_final_rules=True) == 1

    (docs / "QA.md").write_text("QA_PASS\n", encoding="utf-8")
    assert checks.run_docs_checks(tmp_path, str(config), include_final_rules=True) == 0


def _write_final_stage_repo(tmp_path):
    codex = tmp_path / ".codex"
    codex.mkdir()
    (codex / "project-profile.json").write_text(
        json.dumps({"commands": {"test": ["echo test ok"], "build": ["echo build ok"]}}),
        encoding="utf-8",
    )
    phase = tmp_path / "phases" / "1-mvp"
    phase.mkdir(parents=True)
    (tmp_path / "phases" / "index.json").write_text(
        json.dumps({"phases": [{"dir": "1-mvp", "status": "pending"}]}),
        encoding="utf-8",
    )
    (phase / "docs-checks.json").write_text(
        json.dumps(
            {
                "paths": ["docs"],
                "required": [{"name": "ready marker", "pattern": "READY"}],
                "finalRequired": [{"name": "qa marker", "pattern": "QA_PASS"}],
                "forbidden": [{"name": "stale marker", "pattern": "DO_NOT_SHIP"}],
            }
        ),
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PRD.md").write_text("READY\n", encoding="utf-8")


def test_final_stage_fails_when_final_required_docs_rule_is_missing(tmp_path, monkeypatch, capsys):
    _write_final_stage_repo(tmp_path)
    monkeypatch.setattr(checks, "ROOT", tmp_path)

    status = checks.main(["--stage", "final"])

    assert status == 1
    assert "Missing required docs marker: qa marker" in capsys.readouterr().err


def test_final_stage_passes_when_final_required_docs_rule_is_satisfied(tmp_path, monkeypatch, capsys):
    _write_final_stage_repo(tmp_path)
    (tmp_path / "docs" / "QA.md").write_text("QA_PASS\n", encoding="utf-8")
    monkeypatch.setattr(checks, "ROOT", tmp_path)

    status = checks.main(["--stage", "final"])

    assert status == 0
    assert "docs-check passed" in capsys.readouterr().out


def test_manual_stage_does_not_run_final_docs_rules(tmp_path, monkeypatch):
    _write_final_stage_repo(tmp_path)
    monkeypatch.setattr(checks, "ROOT", tmp_path)

    assert checks.main(["--stage", "manual"]) == 0


def test_discover_docs_check_config_prefers_active_phase(tmp_path):
    phase4 = tmp_path / "phases" / "4-old"
    phase5 = tmp_path / "phases" / "5-current"
    phase4.mkdir(parents=True)
    phase5.mkdir(parents=True)
    (tmp_path / "phases" / "index.json").write_text(
        json.dumps({"phases": [{"dir": "4-old", "status": "completed"}, {"dir": "5-current", "status": "pending"}]}),
        encoding="utf-8",
    )
    (phase4 / "docs-checks.json").write_text(json.dumps({"paths": ["docs"], "required": []}), encoding="utf-8")
    (phase5 / "docs-checks.json").write_text(json.dumps({"paths": ["README.md"], "required": []}), encoding="utf-8")

    assert checks.discover_docs_check_config(tmp_path) == phase5 / "docs-checks.json"
