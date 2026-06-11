#!/usr/bin/env python3
"""Inspect whether the Codex operating template is ready to use."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import checks
import codex_common

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FILES = [
    "AGENTS.md",
    "docs/PRD.md",
    "docs/ARCHITECTURE.md",
    "docs/ADR.md",
    "docs/COMMANDS.md",
    "docs/SCOPE_CHANGE_CHECKLIST.md",
    "guides/PROMPTS.md",
    "guides/CONFIGURATION.md",
    "guides/UPGRADE.md",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/project-profile.json",
    ".codex/scope-rules.json",
    ".codex/hooks/tdd-guard.py",
    ".codex/hooks/tdd-guard.sh",
    ".gitattributes",
    ".githooks/pre-commit",
    "phases/README.md",
    "phases/index.json",
    "issues/README.md",
    "archive/README.md",
    "scripts/execute.py",
    "scripts/autopilot.py",
    "scripts/checks.py",
    "scripts/codex_common.py",
    "scripts/doctor.py",
    "scripts/guard.py",
]
TEMPLATE_REQUIRED_FILES = [
    ".github/workflows/template-ci.yml",
]
PLACEHOLDER_FILES = [
    "AGENTS.md",
    "docs/PRD.md",
    "docs/ARCHITECTURE.md",
]
PLACEHOLDER_PATTERN = re.compile(r"<[^>\n]+>|TODO|TBD")
MODES = ("template", "instance")
LEGACY_HOOK_MARKERS = ("/bin/bash", "/usr/bin/python3", "$(git rev-parse")
# phase 파일 형식의 살아있는 예시. SKILL.md 산문과 달리 스키마가 깨지면
# template 모드 doctor(및 CI)가 잡아내므로, 형식 변경 시 예시도 함께 갱신된다.
EXAMPLE_PHASE_DIR = "phases/0-example"
EXAMPLE_PHASE_FILES = (
    "README.md",
    "index.json",
    "docs-checks.json",
    "scope-rules.json",
)
VALID_STEP_STATUSES = {"pending", "completed", "error", "blocked"}


def _status(ok: bool) -> str:
    return "ok" if ok else "missing"


def _git_hooks_path(root: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _count_inline_adrs(root: Path = ROOT) -> int:
    path = root / "docs" / "ADR.md"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("### ADR-"))


def _count_split_adrs(root: Path = ROOT) -> int:
    adr_dir = root / "docs" / "adr"
    if not adr_dir.is_dir():
        return 0
    return len([path for path in adr_dir.glob("*.md") if path.is_file()])


def _has_placeholder(path: Path) -> bool:
    if not path.exists():
        return False
    return bool(PLACEHOLDER_PATTERN.search(path.read_text(encoding="utf-8")))


def _profile_issues(root: Path, mode: str) -> list[str]:
    path = root / ".codex" / "project-profile.json"
    if not path.exists():
        return []
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f".codex/project-profile.json is not valid JSON: {exc}"]

    issues: list[str] = []
    version = str(profile.get("templateVersion", "")).strip()
    if mode == "template":
        # 템플릿 repo에서는 profile의 templateVersion과 harness 상수가 같아야
        # 복사된 인스턴스가 일치한 상태로 시작한다. 한쪽만 올리는 실수를 CI가 잡는다.
        if version != codex_common.TEMPLATE_VERSION:
            issues.append(
                ".codex/project-profile.json templateVersion must equal "
                f"scripts/codex_common.py TEMPLATE_VERSION ({codex_common.TEMPLATE_VERSION})."
            )
        return issues

    project_name = str(profile.get("projectName", "")).strip()
    if not project_name or _is_placeholder(project_name):
        issues.append(".codex/project-profile.json projectName still has a placeholder value.")

    # 설치된 harness 버전(scripts/와 함께 덮어써지는 상수)과 인스턴스의 동기화
    # 기록이 어긋나면 업그레이드가 절반만 끝난 상태다.
    if not version:
        issues.append(
            ".codex/project-profile.json templateVersion is missing. Record the template "
            f"version this instance is synced to (installed harness: {codex_common.TEMPLATE_VERSION})."
        )
    elif version != codex_common.TEMPLATE_VERSION:
        issues.append(
            f".codex/project-profile.json templateVersion '{version}' does not match harness "
            f"TEMPLATE_VERSION '{codex_common.TEMPLATE_VERSION}'. Finish the upgrade steps in the "
            "template guides/UPGRADE.md, then update templateVersion."
        )
    return issues


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.search(value))


def _read_text(root: Path, rel: str) -> str:
    path = root / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _template_contract_issues(root: Path) -> list[str]:
    issues: list[str] = []

    for rel in TEMPLATE_REQUIRED_FILES:
        if not (root / rel).exists():
            issues.append(f"{rel} is missing.")

    hooks_json = _read_text(root, ".codex/hooks.json")
    if "tdd-guard.py" not in hooks_json:
        issues.append(".codex/hooks.json must call the cross-platform tdd-guard.py launcher.")
    if any(marker in hooks_json for marker in LEGACY_HOOK_MARKERS):
        issues.append(".codex/hooks.json still contains legacy POSIX shell hook commands.")

    for rel in (".codex/hooks/tdd-guard.sh", ".githooks/pre-commit"):
        text = _read_text(root, rel)
        if text and any(marker in text for marker in ("/bin/bash", "/usr/bin/python3")):
            issues.append(f"{rel} still contains absolute POSIX shell or Python paths.")

    gitattributes = _read_text(root, ".gitattributes")
    required_attrs = (
        "*.sh text eol=lf",
        ".githooks/* text eol=lf",
        ".codex/hooks/*.sh text eol=lf",
    )
    for attr in required_attrs:
        if attr not in gitattributes:
            issues.append(f".gitattributes must include `{attr}`.")

    scope_rules = root / ".codex" / "scope-rules.json"
    if scope_rules.exists():
        try:
            payload = json.loads(scope_rules.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f".codex/scope-rules.json is not valid JSON: {exc}")
        else:
            if not isinstance(payload, dict):
                issues.append(".codex/scope-rules.json must contain a JSON object.")
            elif "forbidden" in payload and not isinstance(payload["forbidden"], list):
                issues.append(".codex/scope-rules.json `forbidden` must be a list.")

    issues.extend(_example_phase_issues(root))
    return issues


def _example_phase_issues(root: Path) -> list[str]:
    phase_dir = root / EXAMPLE_PHASE_DIR
    if not phase_dir.is_dir():
        return [f"{EXAMPLE_PHASE_DIR}/ example phase is missing."]

    issues: list[str] = []
    for rel in EXAMPLE_PHASE_FILES:
        if not (phase_dir / rel).exists():
            issues.append(f"{EXAMPLE_PHASE_DIR}/{rel} is missing.")

    issues.extend(_example_phase_index_issues(phase_dir))
    issues.extend(_example_docs_checks_issues(root, phase_dir))
    issues.extend(_example_scope_rules_issues(phase_dir))
    return issues


def _example_phase_index_issues(phase_dir: Path) -> list[str]:
    path = phase_dir / "index.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{EXAMPLE_PHASE_DIR}/index.json is not valid JSON: {exc}"]
    if not isinstance(payload, dict):
        return [f"{EXAMPLE_PHASE_DIR}/index.json must contain a JSON object."]

    issues: list[str] = []
    if payload.get("phase") != phase_dir.name:
        issues.append(f"{EXAMPLE_PHASE_DIR}/index.json `phase` must match the directory name.")

    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        issues.append(f"{EXAMPLE_PHASE_DIR}/index.json `steps` must be a non-empty list.")
        return issues

    for entry in steps:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("step"), int)
            or not isinstance(entry.get("name"), str)
        ):
            issues.append(
                f"{EXAMPLE_PHASE_DIR}/index.json steps need an integer `step` and a string `name`."
            )
            continue
        if entry.get("status") not in VALID_STEP_STATUSES:
            issues.append(
                f"{EXAMPLE_PHASE_DIR}/index.json step {entry['step']} status must be one of "
                + ", ".join(sorted(VALID_STEP_STATUSES))
                + "."
            )
        issues.extend(_example_step_file_issues(phase_dir, entry["step"]))
    return issues


def _example_step_file_issues(phase_dir: Path, step_num: int) -> list[str]:
    step_path = phase_dir / f"step{step_num}.md"
    if not step_path.exists():
        return [f"{EXAMPLE_PHASE_DIR}/step{step_num}.md is missing."]

    issues: list[str] = []
    text = step_path.read_text(encoding="utf-8")
    for section in ("## 작업", "## 인수 기준", "## 금지사항"):
        if section not in text:
            issues.append(f"{EXAMPLE_PHASE_DIR}/step{step_num}.md must contain a `{section}` section.")
    if not codex_common.read_acceptance_commands(step_path):
        issues.append(
            f"{EXAMPLE_PHASE_DIR}/step{step_num}.md `## 인수 기준` must contain fenced shell commands."
        )
    return issues


def _example_docs_checks_issues(root: Path, phase_dir: Path) -> list[str]:
    path = phase_dir / "docs-checks.json"
    if not path.exists():
        return []
    try:
        config = checks.load_docs_check_config(root, config_path=str(path))
    except ValueError as exc:
        return [str(exc)]

    issues: list[str] = []
    if not config.paths:
        issues.append(f"{EXAMPLE_PHASE_DIR}/docs-checks.json must define top-level `paths`.")
    for key, rules in (
        ("required", config.required),
        ("finalRequired", config.final_required),
        ("forbidden", config.forbidden),
    ):
        if not rules:
            issues.append(
                f"{EXAMPLE_PHASE_DIR}/docs-checks.json must demonstrate at least one `{key}` rule."
            )
    return issues


def _example_scope_rules_issues(phase_dir: Path) -> list[str]:
    path = phase_dir / "scope-rules.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{EXAMPLE_PHASE_DIR}/scope-rules.json is not valid JSON: {exc}"]
    if not isinstance(payload, dict):
        return [f"{EXAMPLE_PHASE_DIR}/scope-rules.json must contain a JSON object."]

    issues: list[str] = []
    for key in ("extraForbidden", "allowedScopeMessages"):
        rules = payload.get(key)
        if not isinstance(rules, list) or not rules:
            issues.append(
                f"{EXAMPLE_PHASE_DIR}/scope-rules.json must demonstrate at least one `{key}` rule."
            )
            continue
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("message"), str) or not rule["message"]:
                issues.append(
                    f"{EXAMPLE_PHASE_DIR}/scope-rules.json `{key}` rules need a non-empty `message`."
                )
                break
    return issues


def collect_issues(root: Path = ROOT, mode: str = "instance") -> list[str]:
    if mode not in MODES:
        raise ValueError(f"Unknown doctor mode: {mode}")

    issues: list[str] = []

    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            issues.append(f"{rel} is missing.")

    if mode == "instance":
        for rel in PLACEHOLDER_FILES:
            if _has_placeholder(root / rel):
                issues.append(f"{rel} still contains template placeholders.")

    issues.extend(_profile_issues(root, mode))

    if mode == "template":
        issues.extend(_template_contract_issues(root))

    if mode == "instance":
        selected = checks.collect_checks(root, "manual")
        missing = checks.missing_required_checks(selected)
        if missing:
            issues.append(
                "Required check commands are missing: "
                + ", ".join(missing)
                + ". Fill docs/COMMANDS.md or .codex/project-profile.json."
            )

        hooks_path = _git_hooks_path(root)
        if hooks_path != ".githooks":
            issues.append(f"git core.hooksPath is '{hooks_path or 'not configured'}', expected '.githooks'.")
    return issues


def collect_readiness_issues(root: Path = ROOT) -> list[str]:
    return collect_issues(root, "instance")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect Codex operating template or project instance readiness.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--template",
        action="store_const",
        const="template",
        dest="mode",
        help="Validate template repo structure.",
    )
    mode.add_argument(
        "--instance",
        action="store_const",
        const="instance",
        dest="mode",
        help="Validate a copied project instance.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    args = _parse_args(argv)
    profile = checks.load_project_profile(root)
    print("Codex Project Ops Doctor")
    print(f"- mode: {args.mode}")
    print(f"- profile: {profile.get('profile', 'unknown')}")
    profile_version = str(profile.get("templateVersion", "")).strip() or "not recorded"
    print(f"- templateVersion: profile={profile_version}, harness={codex_common.TEMPLATE_VERSION}")
    print(f"- guardMode: {checks.guard_mode(root)}")
    print(f"- git hooksPath: {_git_hooks_path(root) or 'not configured'}")

    print("\nRequired files")
    for rel in REQUIRED_FILES:
        print(f"- {rel}: {_status((root / rel).exists())}")

    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        agents_lines = agents_path.read_text(encoding="utf-8").splitlines()
        print(f"\nAGENTS.md lines: {len(agents_lines)}")
        if len(agents_lines) > 110:
            print("- warning: AGENTS.md is above the 100-line target.")
    else:
        print("\nAGENTS.md lines: missing")

    inline_adrs = _count_inline_adrs(root)
    split_adrs = _count_split_adrs(root)
    print(f"\nADR count: inline={inline_adrs}, split={split_adrs}")
    if inline_adrs > 3 and split_adrs == 0:
        print("- warning: split ADRs into docs/adr/ when ADR count exceeds 3.")

    print("\nSelected checks")
    selected = checks.collect_checks(root, "manual")
    if selected:
        for check in selected:
            print(f"- {check.name}: {check.command} ({check.source})")
    else:
        print("- none configured or detected")

    issues = collect_issues(root, args.mode)
    print(f"\n{args.mode.title()} readiness")
    if not issues:
        print("- ok")
        return 0

    for issue in issues:
        print(f"- blocker: {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
