#!/usr/bin/env python3
"""Inspect whether the Codex operating template is ready to use."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import checks

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FILES = [
    "AGENTS.md",
    "docs/PRD.md",
    "docs/ARCHITECTURE.md",
    "docs/ADR.md",
    "docs/COMMANDS.md",
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
    if mode == "template":
        return issues

    project_name = str(profile.get("projectName", "")).strip()
    if not project_name or _is_placeholder(project_name):
        issues.append(".codex/project-profile.json projectName still has a placeholder value.")
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
