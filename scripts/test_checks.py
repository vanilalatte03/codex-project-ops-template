import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
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

    selected = checks.detect_commands(tmp_path)

    assert selected["test"][0].command == "./gradlew test"
    assert selected["build"][0].command == "./gradlew build"


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
