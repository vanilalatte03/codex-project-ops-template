#!/usr/bin/env python3
"""Inspect whether the Codex operating template is ready to use."""

from __future__ import annotations

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
    ".codex/hooks.json",
    ".codex/project-profile.json",
    ".codex/hooks/tdd-guard.sh",
    ".githooks/pre-commit",
    "phases/README.md",
    "phases/index.json",
    "issues/README.md",
    "scripts/autopilot.py",
]
PLACEHOLDER_FILES = [
    "AGENTS.md",
    "docs/PRD.md",
    "docs/ARCHITECTURE.md",
]
PLACEHOLDER_PATTERN = re.compile(r"<[^>\n]+>|TODO|TBD")


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


def _count_inline_adrs() -> int:
    path = ROOT / "docs" / "ADR.md"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("### ADR-"))


def _count_split_adrs() -> int:
    adr_dir = ROOT / "docs" / "adr"
    if not adr_dir.is_dir():
        return 0
    return len([path for path in adr_dir.glob("*.md") if path.is_file()])


def _has_placeholder(path: Path) -> bool:
    if not path.exists():
        return False
    return bool(PLACEHOLDER_PATTERN.search(path.read_text(encoding="utf-8")))


def _profile_issues(root: Path) -> list[str]:
    path = root / ".codex" / "project-profile.json"
    if not path.exists():
        return []
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f".codex/project-profile.json is not valid JSON: {exc}"]

    issues: list[str] = []
    project_name = str(profile.get("projectName", "")).strip()
    if not project_name or _is_placeholder(project_name):
        issues.append(".codex/project-profile.json projectName still has a placeholder value.")
    return issues


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.search(value))


def collect_readiness_issues(root: Path = ROOT) -> list[str]:
    issues: list[str] = []

    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            issues.append(f"{rel} is missing.")

    for rel in PLACEHOLDER_FILES:
        if _has_placeholder(root / rel):
            issues.append(f"{rel} still contains template placeholders.")

    issues.extend(_profile_issues(root))

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


def main() -> int:
    profile = checks.load_project_profile(ROOT)
    print("Codex Project Ops Doctor")
    print(f"- profile: {profile.get('profile', 'unknown')}")
    print(f"- guardMode: {checks.guard_mode(ROOT)}")
    print(f"- git hooksPath: {_git_hooks_path() or 'not configured'}")

    print("\nRequired files")
    for rel in REQUIRED_FILES:
        print(f"- {rel}: {_status((ROOT / rel).exists())}")

    agents_lines = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    print(f"\nAGENTS.md lines: {len(agents_lines)}")
    if len(agents_lines) > 110:
        print("- warning: AGENTS.md is above the 100-line target.")

    inline_adrs = _count_inline_adrs()
    split_adrs = _count_split_adrs()
    print(f"\nADR count: inline={inline_adrs}, split={split_adrs}")
    if inline_adrs > 3 and split_adrs == 0:
        print("- warning: split ADRs into docs/adr/ when ADR count exceeds 3.")

    print("\nSelected checks")
    selected = checks.collect_checks(ROOT, "manual")
    if selected:
        for check in selected:
            print(f"- {check.name}: {check.command} ({check.source})")
    else:
        print("- none configured or detected")

    issues = collect_readiness_issues(ROOT)
    print("\nReadiness")
    if not issues:
        print("- ok")
        return 0

    for issue in issues:
        print(f"- blocker: {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
