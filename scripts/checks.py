#!/usr/bin/env python3
"""Run project checks from the Codex operating template."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
BASE_CHECK_NAMES = ("lint", "test", "build", "frontend-build")
FINAL_ONLY_CHECK_NAMES = ("harness-test", "docs-check")
CHECK_NAMES = (*BASE_CHECK_NAMES, *FINAL_ONLY_CHECK_NAMES)
REQUIRED_CHECK_NAMES = ("test", "build")
STOP_STAGE_CHECK_NAMES = ("lint",)
STAGES = ("manual", "pre-commit", "stop", "final")
PLACEHOLDER_MARKERS = ("<", ">", "{", "}", "...", "TODO", "TBD")
DEFAULT_CHECK_TIMEOUT = 1800
DOCS_CHECK_CONFIG_NAME = "docs-checks.json"
ACTIVE_PHASE_STATUSES = {"pending", "error", "blocked"}


@dataclass(frozen=True)
class CheckCommand:
    name: str
    command: str
    source: str


@dataclass(frozen=True)
class DocsMatch:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class DocsCheckRule:
    name: str
    pattern: str
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocsCheckConfig:
    source: Path | None
    paths: tuple[str, ...]
    skip_dirs: frozenset[str]
    skip_suffixes: frozenset[str]
    required: tuple[DocsCheckRule, ...]
    final_required: tuple[DocsCheckRule, ...]
    forbidden: tuple[DocsCheckRule, ...]


def load_project_profile(root: Path = ROOT) -> dict:
    path = root / ".codex" / "project-profile.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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
        for name in (
            "gradlew",
            "gradlew.bat",
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
        )
    )
    has_maven = any((root / name).exists() for name in ("mvnw", "mvnw.cmd", "mvnw.bat", "pom.xml"))

    if has_gradle:
        if sys.platform.startswith("win"):
            gradle = ".\\gradlew.bat" if (root / "gradlew.bat").exists() else "gradle"
        else:
            gradle = "./gradlew" if (root / "gradlew").exists() else "gradle"
        _append(result, "test", f"{gradle} test", "detected:spring-gradle")
        _append(result, "build", f"{gradle} build", "detected:spring-gradle")
        return

    if has_maven:
        if sys.platform.startswith("win"):
            if (root / "mvnw.cmd").exists():
                maven = ".\\mvnw.cmd"
            elif (root / "mvnw.bat").exists():
                maven = ".\\mvnw.bat"
            else:
                maven = "mvn"
        else:
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


def check_names_for_stage(stage: str, root: Path = ROOT) -> tuple[str, ...]:
    if stage == "final":
        default = CHECK_NAMES
    elif stage == "stop":
        # stop 훅은 에이전트가 멈출 때마다 실행되므로 기본은 lint만 돌린다.
        # test/build까지 돌리려면 stageChecks로 명시적으로 확장한다.
        default = STOP_STAGE_CHECK_NAMES
    else:
        default = BASE_CHECK_NAMES

    # Per-stage overrides keep heavy stages (e.g. stop hooks) configurable:
    # .codex/project-profile.json -> {"stageChecks": {"stop": ["lint"]}}
    stage_checks = load_project_profile(root).get("stageChecks")
    if not isinstance(stage_checks, dict):
        return default
    configured = stage_checks.get(stage)
    if not isinstance(configured, list):
        return default
    selected = tuple(name for name in configured if name in CHECK_NAMES)
    return selected or default


def _flatten(commands: dict[str, list[CheckCommand]], names: Iterable[str] = CHECK_NAMES) -> list[CheckCommand]:
    return [command for name in names for command in commands.get(name, [])]


def collect_checks(root: Path = ROOT, stage: str = "manual") -> list[CheckCommand]:
    names = check_names_for_stage(stage, root)
    merged: dict[str, list[CheckCommand]] = {}
    for provider in (commands_from_profile, commands_from_docs, detect_commands):
        for name, commands in provider(root).items():
            # First provider that defines a check name wins for that name only,
            # so a profile that pins `test` does not silence docs/detected `build`.
            merged.setdefault(name, commands)
    return _flatten(merged, names)


def missing_required_checks(checks: Iterable[CheckCommand]) -> list[str]:
    present = {check.name for check in checks}
    return [name for name in REQUIRED_CHECK_NAMES if name not in present]


def _docs_config_path(root: Path = ROOT, config_path: str | None = None) -> Path | None:
    if config_path:
        path = Path(config_path)
        return path if path.is_absolute() else root / path
    return discover_docs_check_config(root)


def _phase_docs_check_path(root: Path, phase_dir: str) -> Path:
    return root / "phases" / phase_dir / DOCS_CHECK_CONFIG_NAME


def _phase_index_entries(root: Path = ROOT) -> list[dict]:
    path = root / "phases" / "index.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    phases = payload.get("phases") if isinstance(payload, dict) else None
    if not isinstance(phases, list):
        return []
    return [phase for phase in phases if isinstance(phase, dict)]


def discover_docs_check_config(root: Path = ROOT) -> Path | None:
    phases = _phase_index_entries(root)
    for phase in phases:
        phase_dir = phase.get("dir")
        status = phase.get("status")
        if not isinstance(phase_dir, str) or status not in ACTIVE_PHASE_STATUSES:
            continue
        config_path = _phase_docs_check_path(root, phase_dir)
        if config_path.exists():
            return config_path

    for phase in reversed(phases):
        phase_dir = phase.get("dir")
        if not isinstance(phase_dir, str):
            continue
        config_path = _phase_docs_check_path(root, phase_dir)
        if config_path.exists():
            return config_path

    phase_configs = sorted((root / "phases").glob(f"*/{DOCS_CHECK_CONFIG_NAME}"))
    return phase_configs[-1] if phase_configs else None


def _strings_from_value(value: object, default: Iterable[str] = ()) -> tuple[str, ...]:
    values = value if isinstance(value, list) else list(default)
    return tuple(item for item in values if isinstance(item, str) and item)


def _config_strings(config: dict, key: str, default: Iterable[str] = ()) -> tuple[str, ...]:
    values = config.get(key, list(default))
    if not isinstance(values, list):
        return tuple(default)
    return _strings_from_value(values, default)


def _config_rules(config: dict, key: str) -> tuple[DocsCheckRule, ...]:
    values = config.get(key, [])
    if not isinstance(values, list):
        return ()

    rules: list[DocsCheckRule] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        name = value.get("name")
        pattern = value.get("pattern")
        paths = _strings_from_value(value.get("paths", []))
        if isinstance(name, str) and name and isinstance(pattern, str) and pattern:
            rules.append(DocsCheckRule(name, pattern, paths))
    return tuple(rules)


def load_docs_check_config(root: Path = ROOT, config_path: str | None = None) -> DocsCheckConfig:
    path = _docs_config_path(root, config_path)
    if path is None or not path.exists():
        return DocsCheckConfig(None, (), frozenset(), frozenset(), (), (), ())

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"{path} must contain a JSON object")

    return DocsCheckConfig(
        source=path,
        paths=_config_strings(config, "paths"),
        skip_dirs=frozenset(_config_strings(config, "skipDirs")),
        skip_suffixes=frozenset(_config_strings(config, "skipSuffixes")),
        required=_config_rules(config, "required"),
        final_required=_config_rules(config, "finalRequired"),
        forbidden=_config_rules(config, "forbidden"),
    )


def _is_docs_check_file(path: Path, config: DocsCheckConfig) -> bool:
    return (
        path.is_file()
        and path.suffix not in config.skip_suffixes
        and not any(part in config.skip_dirs for part in path.parts)
    )


def _iter_docs_check_files(
    root: Path,
    config: DocsCheckConfig,
    paths: Iterable[str] | None = None,
) -> Iterable[Path]:
    selected_paths = tuple(paths or config.paths)
    for item in selected_paths:
        target = root / item
        if not target.exists():
            continue
        if target.is_file():
            if _is_docs_check_file(target, config):
                yield target
            continue
        for path in sorted(target.rglob("*")):
            if _is_docs_check_file(path, config):
                yield path


def _find_docs_matches(
    root: Path,
    config: DocsCheckConfig,
    pattern: str,
    paths: Iterable[str] | None = None,
) -> list[DocsMatch]:
    regex = re.compile(pattern)
    matches: list[DocsMatch] = []
    for path in _iter_docs_check_files(root, config, paths):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        for line_number, line in enumerate(lines, start=1):
            if regex.search(line):
                matches.append(DocsMatch(relative, line_number, line.strip()))
    return matches


def _format_docs_matches(matches: list[DocsMatch], *, limit: int = 10) -> str:
    rendered = [f"{match.path}:{match.line}: {match.text}" for match in matches[:limit]]
    if len(matches) > limit:
        rendered.append(f"... and {len(matches) - limit} more")
    return "\n".join(f"  {line}" for line in rendered)


def run_docs_checks(root: Path = ROOT, config_path: str | None = None, include_final_rules: bool = False) -> int:
    failures: list[str] = []
    try:
        config = load_docs_check_config(root, config_path)
    except ValueError as exc:
        print(f"docs-check failed: {exc}", file=sys.stderr)
        return 1

    required_rules = config.required + (config.final_required if include_final_rules else ())
    rules = (*required_rules, *config.forbidden)
    has_paths = bool(config.paths or any(rule.paths for rule in rules))
    if not has_paths or not rules:
        source = config.source or f"phases/*/{DOCS_CHECK_CONFIG_NAME}"
        print(f"docs-check skipped: no rules configured in {source}.")
        return 0

    for rule in required_rules:
        if not _find_docs_matches(root, config, rule.pattern, rule.paths):
            failures.append(f"Missing required docs marker: {rule.name}")

    for rule in config.forbidden:
        matches = _find_docs_matches(root, config, rule.pattern, rule.paths)
        if matches:
            failures.append(f"Forbidden docs marker found: {rule.name}\n{_format_docs_matches(matches)}")

    if failures:
        print("docs-check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"docs-check passed. ({config.source})")
    return 0


def run_checks(
    checks: Iterable[CheckCommand],
    root: Path = ROOT,
    timeout: int = DEFAULT_CHECK_TIMEOUT,
    require_required: bool = True,
) -> int:
    checks = list(checks)
    if require_required:
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

    if not checks:
        print(f"No {'/'.join(CHECK_NAMES)} commands configured or detected.")
        return 0

    for check in checks:
        print(f"$ {check.command}  # {check.name}, {check.source}")
        sys.stdout.flush()
        try:
            # Stream output directly so long builds show live progress.
            result = subprocess.run(check.command, cwd=root, shell=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"Command timed out after {timeout}s: {check.command}", file=sys.stderr)
            return 124
        if result.returncode != 0:
            print(f"Command failed with exit code {result.returncode}: {check.command}", file=sys.stderr)
            return result.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run project checks for the Codex operating template.")
    parser.add_argument("--stage", choices=STAGES, default="manual")
    parser.add_argument("--list", action="store_true", help="Print selected commands without running them.")
    parser.add_argument("--docs-check", action="store_true", help="Run config-driven docs consistency checks only.")
    parser.add_argument(
        "--docs-check-config",
        help=f"Docs-check config path. Defaults to phases/<current-phase>/{DOCS_CHECK_CONFIG_NAME}.",
    )
    parser.add_argument(
        "--include-final-docs",
        action="store_true",
        help="Include final-only docs-check rules.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_CHECK_TIMEOUT,
        help="Per-command timeout in seconds.",
    )
    args = parser.parse_args(argv)

    if args.docs_check:
        return run_docs_checks(ROOT, args.docs_check_config, args.include_final_docs)

    checks = collect_checks(ROOT, args.stage)
    if args.list:
        for check in checks:
            print(f"{check.name}\t{check.command}\t{check.source}")
        if not checks:
            print("No lint/test/build commands configured or detected.")
        return 0
    require_required = args.stage in {"manual", "pre-commit", "final"}
    return run_checks(checks, ROOT, timeout=args.timeout, require_required=require_required)


if __name__ == "__main__":
    raise SystemExit(main())
