#!/usr/bin/env python3
"""Run project checks from the Codex operating template."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
CHECK_NAMES = ("lint", "test", "build")
REQUIRED_CHECK_NAMES = ("test", "build")
PLACEHOLDER_MARKERS = ("<", ">", "{", "}", "...", "TODO", "TBD")


@dataclass(frozen=True)
class CheckCommand:
    name: str
    command: str
    source: str


def load_project_profile(root: Path = ROOT) -> dict:
    path = root / ".codex" / "project-profile.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def guard_mode(root: Path = ROOT) -> str:
    mode = str(load_project_profile(root).get("guardMode", "soft")).lower()
    return "hard" if mode == "hard" else "soft"


def _as_command_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def is_real_command(command: str) -> bool:
    cleaned = command.strip().strip("`")
    if not cleaned:
        return False
    if cleaned.lower() in {"none", "n/a", "na", "-"}:
        return False
    return not any(marker in cleaned for marker in PLACEHOLDER_MARKERS)


def _append(target: dict[str, list[CheckCommand]], name: str, command: str, source: str):
    command = command.strip().strip("`")
    if name in CHECK_NAMES and is_real_command(command):
        target.setdefault(name, []).append(CheckCommand(name, command, source))


def commands_from_profile(root: Path = ROOT) -> dict[str, list[CheckCommand]]:
    profile = load_project_profile(root)
    commands = profile.get("commands", {})
    result: dict[str, list[CheckCommand]] = {}
    if not isinstance(commands, dict):
        return result

    for name in CHECK_NAMES:
        for command in _as_command_list(commands.get(name)):
            _append(result, name, command, ".codex/project-profile.json")
    return result


def commands_from_docs(root: Path = ROOT) -> dict[str, list[CheckCommand]]:
    path = root / "docs" / "COMMANDS.md"
    if not path.exists():
        return {}

    result: dict[str, list[CheckCommand]] = {}
    in_active_table = False
    in_code_block = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if line.startswith("## "):
            in_active_table = line == "## 활성 명령"
            continue
        if not in_active_table or not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, command = cells[0], cells[1]
        if name in {"---", "이름"}:
            continue
        _append(result, name, command, "docs/COMMANDS.md")

    return result


def _package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def _node_script_command(pm: str, script: str) -> str:
    if pm == "npm":
        return "npm test" if script == "test" else f"npm run {script}"
    return f"{pm} {script}"


def _detect_node(root: Path, result: dict[str, list[CheckCommand]]):
    package_json = root / "package.json"
    if not package_json.exists():
        return
    try:
        package = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        return

    pm = _package_manager(root)
    for name in CHECK_NAMES:
        if name in scripts:
            _append(result, name, _node_script_command(pm, name), f"detected:{pm}")


def _detect_spring(root: Path, result: dict[str, list[CheckCommand]]):
    has_gradle = any(
        (root / name).exists()
        for name in ("gradlew", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
    )
    has_maven = any((root / name).exists() for name in ("mvnw", "pom.xml"))

    if has_gradle:
        gradle = "./gradlew" if (root / "gradlew").exists() else "gradle"
        _append(result, "test", f"{gradle} test", "detected:spring-gradle")
        _append(result, "build", f"{gradle} build", "detected:spring-gradle")
        return

    if has_maven:
        maven = "./mvnw" if (root / "mvnw").exists() else "mvn"
        _append(result, "test", f"{maven} test", "detected:spring-maven")
        _append(result, "build", f"{maven} package", "detected:spring-maven")


def _detect_python(root: Path, result: dict[str, list[CheckCommand]]):
    has_python_project = any((root / name).exists() for name in ("pyproject.toml", "uv.lock", "requirements.txt"))
    has_tests = any((root / name).exists() for name in ("tests", "test"))
    if not (has_python_project or has_tests):
        return

    has_uv = shutil.which("uv") is not None
    has_ruff = shutil.which("ruff") is not None
    python_test = "uv run pytest" if has_uv and (root / "pyproject.toml").exists() else "python -m pytest"
    _append(result, "test", python_test, "detected:python")

    if has_uv and (root / "pyproject.toml").exists():
        _append(result, "lint", "uv run ruff check .", "detected:python")
    elif has_ruff:
        _append(result, "lint", "ruff check .", "detected:python")


def detect_commands(root: Path = ROOT) -> dict[str, list[CheckCommand]]:
    result: dict[str, list[CheckCommand]] = {}
    _detect_spring(root, result)
    _detect_python(root, result)
    _detect_node(root, result)
    return result


def _flatten(commands: dict[str, list[CheckCommand]]) -> list[CheckCommand]:
    return [command for name in CHECK_NAMES for command in commands.get(name, [])]


def collect_checks(root: Path = ROOT, stage: str = "manual") -> list[CheckCommand]:
    del stage  # stages share the same lint/test/build order for now.
    providers = [
        commands_from_profile(root),
        commands_from_docs(root),
        detect_commands(root),
    ]
    selected: dict[str, list[CheckCommand]] = {}
    for name in CHECK_NAMES:
        for commands in providers:
            if commands.get(name):
                selected[name] = commands[name]
                break
    return _flatten(selected)


def missing_required_checks(checks: Iterable[CheckCommand]) -> list[str]:
    present = {check.name for check in checks}
    return [name for name in REQUIRED_CHECK_NAMES if name not in present]


def run_checks(checks: Iterable[CheckCommand], root: Path = ROOT) -> int:
    checks = list(checks)
    missing = missing_required_checks(checks)
    if missing:
        available = ", ".join(check.name for check in checks) or "none"
        print(
            "Missing required check commands: "
            + ", ".join(missing)
            + ". Configure docs/COMMANDS.md or .codex/project-profile.json. "
            + f"Available checks: {available}.",
            file=sys.stderr,
        )
        return 1

    for check in checks:
        print(f"$ {check.command}  # {check.name}, {check.source}")
        result = subprocess.run(
            check.command,
            cwd=root,
            shell=True,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            print(f"Command failed with exit code {result.returncode}: {check.command}", file=sys.stderr)
            return result.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run project checks for the Codex operating template.")
    parser.add_argument("--stage", choices=("manual", "pre-commit", "stop"), default="manual")
    parser.add_argument("--list", action="store_true", help="Print selected commands without running them.")
    args = parser.parse_args(argv)

    checks = collect_checks(ROOT, args.stage)
    if args.list:
        for check in checks:
            print(f"{check.name}\t{check.command}\t{check.source}")
        if not checks:
            print("No lint/test/build commands configured or detected.")
        return 0
    return run_checks(checks, ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
