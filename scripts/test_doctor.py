import json
import sys
from pathlib import Path

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


def test_readiness_passes_when_docs_and_required_commands_ready(tmp_path, monkeypatch):
    _write_ready_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: ".githooks")

    assert doctor.collect_readiness_issues(tmp_path) == []
