import json
from pathlib import Path

import pytest

import upgrade


def _make_template(root: Path, version: str = "2026.07.01") -> Path:
    template = root / "template"
    # 템플릿 소유 디렉터리/파일 일부 + 버전 상수.
    (template / "scripts").mkdir(parents=True)
    (template / "scripts" / "codex_common.py").write_text(
        f'TEMPLATE_VERSION = "{version}"\n', encoding="utf-8"
    )
    (template / "scripts" / "upgrade.py").write_text("# new\n", encoding="utf-8")
    (template / ".agents" / "skills" / "harness").mkdir(parents=True)
    (template / ".agents" / "skills" / "harness" / "SKILL.md").write_text("new harness\n", encoding="utf-8")
    (template / ".githooks").mkdir()
    (template / ".githooks" / "pre-commit").write_text("new hook\n", encoding="utf-8")
    (template / ".codex" / "hooks").mkdir(parents=True)
    (template / ".codex" / "hooks" / "tdd-guard.py").write_text("new guard\n", encoding="utf-8")
    (template / ".codex" / "hooks.json").write_text("{}\n", encoding="utf-8")
    (template / "guides").mkdir()
    (template / "guides" / "UPGRADE.md").write_text("new upgrade doc\n", encoding="utf-8")
    # 템플릿 전용 — 복사되면 안 됨.
    (template / ".github" / "workflows").mkdir(parents=True)
    (template / ".github" / "workflows" / "template-ci.yml").write_text("ci\n", encoding="utf-8")
    return template


def _make_instance(root: Path, version: str = "2026.06.12") -> Path:
    instance = root / "instance"
    (instance / "scripts").mkdir(parents=True)
    (instance / "scripts" / "codex_common.py").write_text(
        f'TEMPLATE_VERSION = "{version}"\n', encoding="utf-8"
    )
    (instance / "scripts" / "stale.py").write_text("old\n", encoding="utf-8")
    (instance / ".agents" / "skills" / "myproject").mkdir(parents=True)
    (instance / ".agents" / "skills" / "myproject" / "SKILL.md").write_text("project skill\n", encoding="utf-8")
    (instance / ".codex").mkdir(exist_ok=True)
    (instance / ".codex" / "project-profile.json").write_text(
        json.dumps({"projectName": "demo", "templateVersion": version, "guardMode": "soft"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (instance / "docs").mkdir()
    (instance / "docs" / "PRD.md").write_text("project PRD\n", encoding="utf-8")
    return instance


def test_apply_overwrites_template_units_and_preserves_project(tmp_path):
    template = _make_template(tmp_path)
    instance = _make_instance(tmp_path)

    exit_code = upgrade.main(["--from", str(template)], instance_root=instance)

    assert exit_code == 0
    # 템플릿 소유 단위는 덮어써진다.
    assert (instance / "scripts" / "upgrade.py").read_text(encoding="utf-8") == "# new\n"
    assert (instance / "guides" / "UPGRADE.md").read_text(encoding="utf-8") == "new upgrade doc\n"
    # wholesale 교체이므로 템플릿에서 사라진 파일은 인스턴스에서도 제거된다.
    assert not (instance / "scripts" / "stale.py").exists()
    # 프로젝트 소유 파일은 보존된다.
    assert (instance / "docs" / "PRD.md").read_text(encoding="utf-8") == "project PRD\n"
    assert (instance / ".agents" / "skills" / "myproject" / "SKILL.md").exists()
    # 템플릿 전용 파일은 복사되지 않는다.
    assert not (instance / ".github" / "workflows" / "template-ci.yml").exists()
    # templateVersion 갱신, 다른 키 보존.
    profile = json.loads((instance / ".codex" / "project-profile.json").read_text(encoding="utf-8"))
    assert profile["templateVersion"] == "2026.07.01"
    assert profile["projectName"] == "demo"


def test_dry_run_changes_nothing(tmp_path):
    template = _make_template(tmp_path)
    instance = _make_instance(tmp_path)

    exit_code = upgrade.main(["--from", str(template), "--dry-run"], instance_root=instance)

    assert exit_code == 0
    assert (instance / "scripts" / "stale.py").exists()
    assert (instance / "scripts" / "upgrade.py").exists() is False
    profile = json.loads((instance / ".codex" / "project-profile.json").read_text(encoding="utf-8"))
    assert profile["templateVersion"] == "2026.06.12"


def test_refuses_self_upgrade(tmp_path):
    instance = _make_instance(tmp_path)
    exit_code = upgrade.main(["--from", str(instance)], instance_root=instance)
    assert exit_code == 1


def test_blocks_when_template_missing(tmp_path):
    instance = _make_instance(tmp_path)
    missing = tmp_path / "nope"
    exit_code = upgrade.main(["--from", str(missing)], instance_root=instance)
    assert exit_code == 1
