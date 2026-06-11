import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import codex_common
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
        json.dumps(
            {
                "projectName": "demo",
                "templateVersion": codex_common.TEMPLATE_VERSION,
                "guardMode": "soft",
                "commands": {},
            }
        ),
        encoding="utf-8",
    )
    (root / ".codex" / "scope-rules.json").write_text(
        json.dumps({"forbidden": []}),
        encoding="utf-8",
    )
    _write_cross_platform_hook_contract(root)


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
        json.dumps(
            {
                "projectName": "<project-name>",
                "templateVersion": codex_common.TEMPLATE_VERSION,
                "guardMode": "soft",
                "commands": {},
            }
        ),
        encoding="utf-8",
    )
    (root / ".codex" / "scope-rules.json").write_text(
        json.dumps({"forbidden": []}),
        encoding="utf-8",
    )
    _write_cross_platform_hook_contract(root)
    _write_example_phase(root)


def _write_example_phase(root: Path):
    phase_dir = root / "phases" / "0-example"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "README.md").write_text(
        "# Phase: 0-example\n\n## 목표\n- 예시 목표\n\n## 완료 기준\n- 예시 기준\n",
        encoding="utf-8",
    )
    (phase_dir / "index.json").write_text(
        json.dumps(
            {
                "project": "<프로젝트명>",
                "phase": "0-example",
                "steps": [{"step": 0, "name": "project-setup", "status": "pending"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (phase_dir / "step0.md").write_text(
        "\n".join(
            [
                "# 단계 0: project-setup",
                "",
                "## 작업",
                "예시 작업을 수행한다.",
                "",
                "## 인수 기준",
                "",
                "```bash",
                "python scripts/checks.py --stage manual",
                "```",
                "",
                "## 금지사항",
                "- 범위 밖 기능을 추가하지 마라.",
            ]
        ),
        encoding="utf-8",
    )
    (phase_dir / "docs-checks.json").write_text(
        json.dumps(
            {
                "paths": ["phases/0-example"],
                "required": [{"name": "goal", "pattern": "^## 목표$"}],
                "finalRequired": [{"name": "done", "pattern": "^## 완료 기준$"}],
                "forbidden": [{"name": "stale", "pattern": "deprecated-example-api"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (phase_dir / "scope-rules.json").write_text(
        json.dumps(
            {
                "extraForbidden": [{"message": "범위 밖 기능", "anyLowered": ["sync-service"]}],
                "allowedScopeMessages": [{"message": "범위 밖 기능", "steps": [0]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_cross_platform_hook_contract(root: Path):
    (root / ".codex" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python .codex/hooks/tdd-guard.py stop",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (root / ".codex" / "hooks" / "tdd-guard.py").write_text("ready\n", encoding="utf-8")
    (root / ".codex" / "hooks" / "tdd-guard.sh").write_text(
        "#!/usr/bin/env sh\npython3 \"$repo_root/.codex/hooks/tdd-guard.py\" \"$@\"\n",
        encoding="utf-8",
    )
    (root / ".githooks" / "pre-commit").write_text(
        "#!/usr/bin/env sh\nexec sh \"$repo_root/.codex/hooks/tdd-guard.sh\" git-pre-commit\n",
        encoding="utf-8",
    )
    (root / ".gitattributes").write_text(
        "*.sh text eol=lf\n.githooks/* text eol=lf\n.codex/hooks/*.sh text eol=lf\n",
        encoding="utf-8",
    )
    workflow = root / ".github" / "workflows" / "template-ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("name: Template CI\n", encoding="utf-8")


def test_required_files_cover_readme_core_operations_contract():
    expected = {
        ".codex/config.toml",
        "scripts/execute.py",
        "scripts/autopilot.py",
        "scripts/checks.py",
        "scripts/codex_common.py",
        "scripts/doctor.py",
        "scripts/guard.py",
    }

    assert expected.issubset(set(doctor.REQUIRED_FILES))


@pytest.mark.parametrize(
    "missing_rel",
    [
        ".codex/config.toml",
        "scripts/execute.py",
        "scripts/checks.py",
        "scripts/codex_common.py",
        "scripts/doctor.py",
        "scripts/guard.py",
    ],
)
def test_readiness_detects_missing_core_operations_files(tmp_path, monkeypatch, missing_rel):
    _write_ready_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: ".githooks")
    (tmp_path / missing_rel).unlink()

    issues = doctor.collect_issues(tmp_path, "instance")

    assert f"{missing_rel} is missing." in issues


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


def test_template_mode_detects_legacy_hook_command(tmp_path):
    _write_template_files(tmp_path)
    (tmp_path / ".codex" / "hooks.json").write_text(
        '{ "command": "/bin/bash \\"$(git rev-parse --show-toplevel)/.codex/hooks/tdd-guard.sh\\" stop" }',
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "template")

    assert any("cross-platform tdd-guard.py" in issue for issue in issues)
    assert any("legacy POSIX shell hook commands" in issue for issue in issues)


def test_template_mode_detects_missing_line_ending_policy(tmp_path):
    _write_template_files(tmp_path)
    (tmp_path / ".gitattributes").write_text("*.py text eol=lf\n", encoding="utf-8")

    issues = doctor.collect_issues(tmp_path, "template")

    assert any(".githooks/* text eol=lf" in issue for issue in issues)


def test_template_mode_detects_missing_example_phase(tmp_path, monkeypatch):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")
    shutil.rmtree(tmp_path / "phases" / "0-example")

    issues = doctor.collect_issues(tmp_path, "template")

    assert "phases/0-example/ example phase is missing." in issues


def test_template_mode_detects_example_index_schema_violations(tmp_path, monkeypatch):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")
    (tmp_path / "phases" / "0-example" / "index.json").write_text(
        json.dumps(
            {
                "project": "<프로젝트명>",
                "phase": "wrong-name",
                "steps": [{"step": 1, "name": "missing-step-file", "status": "running"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "template")

    assert any("`phase` must match the directory name" in issue for issue in issues)
    assert any("step 1 status must be one of" in issue for issue in issues)
    assert "phases/0-example/step1.md is missing." in issues


def test_template_mode_detects_example_step_without_acceptance_commands(tmp_path, monkeypatch):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")
    (tmp_path / "phases" / "0-example" / "step0.md").write_text(
        "# 단계 0\n\n## 작업\n예시\n\n## 인수 기준\n없음\n\n## 금지사항\n- 없음\n",
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "template")

    assert any("must contain fenced shell commands" in issue for issue in issues)


def test_template_mode_requires_example_rules_for_each_docs_check_type(tmp_path, monkeypatch):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")
    (tmp_path / "phases" / "0-example" / "docs-checks.json").write_text(
        json.dumps({"paths": ["phases/0-example"], "required": [], "finalRequired": [], "forbidden": []}),
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "template")

    for key in ("required", "finalRequired", "forbidden"):
        assert any(f"`{key}` rule" in issue for issue in issues)


def test_template_mode_detects_invalid_example_scope_rules(tmp_path, monkeypatch):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")
    (tmp_path / "phases" / "0-example" / "scope-rules.json").write_text(
        json.dumps({"extraForbidden": [{"anyLowered": ["sync"]}], "allowedScopeMessages": []}),
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "template")

    assert any("`extraForbidden` rules need a non-empty `message`" in issue for issue in issues)
    assert any("`allowedScopeMessages` rule" in issue for issue in issues)


def test_instance_mode_detects_missing_template_version(tmp_path, monkeypatch):
    _write_ready_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: ".githooks")
    (tmp_path / ".codex" / "project-profile.json").write_text(
        json.dumps({"projectName": "demo", "guardMode": "soft", "commands": {}}),
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "instance")

    assert any("templateVersion is missing" in issue for issue in issues)


def test_instance_mode_detects_template_version_mismatch(tmp_path, monkeypatch):
    _write_ready_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: ".githooks")
    (tmp_path / ".codex" / "project-profile.json").write_text(
        json.dumps(
            {
                "projectName": "demo",
                "templateVersion": "1900.01.01",
                "guardMode": "soft",
                "commands": {},
            }
        ),
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "instance")

    assert any(
        "templateVersion '1900.01.01' does not match harness TEMPLATE_VERSION" in issue
        for issue in issues
    )


def test_template_mode_detects_template_version_drift(tmp_path, monkeypatch):
    _write_template_files(tmp_path)
    monkeypatch.setattr(doctor, "_git_hooks_path", lambda root=tmp_path: "")
    (tmp_path / ".codex" / "project-profile.json").write_text(
        json.dumps(
            {
                "projectName": "<project-name>",
                "templateVersion": "1900.01.01",
                "guardMode": "soft",
                "commands": {},
            }
        ),
        encoding="utf-8",
    )

    issues = doctor.collect_issues(tmp_path, "template")

    assert any(
        "templateVersion must equal scripts/codex_common.py TEMPLATE_VERSION" in issue
        for issue in issues
    )


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
