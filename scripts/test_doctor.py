import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import doctor


def _write_ready_files(root: Path):
    for rel in doctor.REQUIRED_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ready\n", encoding="utf-8")

    (root / "AGENTS.md").write_text("# 프로젝트: Demo\n\n## 목표\n- Demo goal\n", encoding="utf-8")
    (root / "docs" / "PRD.md").write_text("# PRD: Demo\n\n## MVP 범위\n1. Demo\n", encoding="utf-8")
    (root / "docs" / "ARCHITECTURE.md").write_text(
        "# 아키텍처\n\n## 시스템 개요\n- Runtime/Framework: Python\n",
        encoding="utf-8",
    )
    (root / "docs" / "COMMANDS.md").write_text(
        """
## 활성 명령
| 이름 | 명령 | 필수 | 설명 |
| --- | --- | --- | --- |
| test | `python3 -m pytest` | yes | tests |
| build | `python3 -m compileall scripts` | yes | build |
""".strip(),
        encoding="utf-8",
    )
    (root / ".codex" / "project-profile.json").write_text(
        json.dumps({"projectName": "demo", "guardMode": "soft", "commands": {}}),
        encoding="utf-8",
    )


def _write_template_files(root: Path):
    for rel in doctor.REQUIRED_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ready\n", encoding="utf-8")

    (root / "AGENTS.md").write_text("# 프로젝트: <프로젝트명>\n", encoding="utf-8")
    (root / "docs" / "PRD.md").write_text("# PRD: <프로젝트명>\n", encoding="utf-8")
    (root / "docs" / "ARCHITECTURE.md").write_text(
        "# 아키텍처\n\n## 시스템 개요\n- Runtime/Framework: <Spring Boot | Python | Node | 기타>\n",
        encoding="utf-8",
    )
    (root / "docs" / "COMMANDS.md").write_text("# Commands\n", encoding="utf-8")
    (root / ".codex" / "project-profile.json").write_text(
        json.dumps({"projectName": "<project-name>", "guardMode": "soft", "commands": {}}),
        encoding="utf-8",
    )


def test_readiness_issues_detect_placeholders_and_missing_commands(tmp_path, monkeypatch):
    _write_ready_files(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# 프로젝트: <프로젝트명>\n", encoding="utf-8")
    (tmp_path / "docs" / "COMMANDS.md").write_text("# Commands\n", encoding="utf-8")
    (tmp_path / ".codex" / "project-profile.json").write_text(
        json.dumps({"projectName": "<project-name>"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: ".githooks")

    issues = doctor.collect_readiness_issues(tmp_path)

    assert any("AGENTS.md still contains template placeholders" in issue for issue in issues)
    assert any("projectName still has a placeholder" in issue for issue in issues)
    assert any("Required check commands are missing" in issue for issue in issues)
    assert doctor.collect_issues(tmp_path, "instance") == issues


def test_readiness_passes_when_docs_and_required_commands_ready(tmp_path, monkeypatch):
    _write_ready_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: ".githooks")

    assert doctor.collect_readiness_issues(tmp_path) == []


def test_template_mode_allows_placeholders_missing_commands_and_unconfigured_hooks(tmp_path, monkeypatch):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")

    assert doctor.collect_issues(tmp_path, "template") == []


def test_template_mode_detects_missing_required_files(tmp_path):
    _write_template_files(tmp_path)
    (tmp_path / "AGENTS.md").unlink()

    issues = doctor.collect_issues(tmp_path, "template")

    assert "AGENTS.md is missing." in issues


def test_template_mode_detects_invalid_project_profile_json(tmp_path):
    _write_template_files(tmp_path)
    (tmp_path / ".codex" / "project-profile.json").write_text("{", encoding="utf-8")

    issues = doctor.collect_issues(tmp_path, "template")

    assert any(".codex/project-profile.json is not valid JSON" in issue for issue in issues)


def test_main_requires_explicit_mode():
    with pytest.raises(SystemExit) as exc_info:
        doctor.main([])

    assert exc_info.value.code == 2


def test_main_template_and_instance_modes_return_expected_codes(tmp_path, monkeypatch, capsys):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")

    assert doctor.main(["--template"], root=tmp_path) == 0
    assert doctor.main(["--instance"], root=tmp_path) == 1
    output = capsys.readouterr().out
    assert "- mode: template" in output
    assert "- mode: instance" in output
