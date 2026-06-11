#!/usr/bin/env python3
"""Codex and Git hook policy for the operating template."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import checks

ROOT = Path(__file__).resolve().parent.parent
SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
SKIP_PREFIXES = (".agents/", ".codex/", ".git/", ".githooks/", "docs/", "phases/", "issues/")
SKIP_NAMES = {
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
    "uv.lock",
    "yarn.lock",
}
# Best-effort filter: it blocks obvious dangerous forms but cannot catch every
# shell indirection (variables, eval, command substitution). Treat it as a
# safety net, not a security boundary.
DANGEROUS_RULES = [
    (
        re.compile(
            r"\brm\b(?=[^\n;&|]*\s(?:-[A-Za-z]*r[A-Za-z]*|--recursive)\b)"
            r"(?=[^\n;&|]*\s(?:-[A-Za-z]*f[A-Za-z]*|--force)\b)"
        ),
        "recursive forced removal is blocked",
    ),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "hard resets are blocked"),
    (re.compile(r"\bgit\s+clean\s+-[A-Za-z]*[fdx][A-Za-z]*\b"), "git clean with file deletion is blocked"),
    (re.compile(r"\bgit\s+push\b[^\n;&|]*\s--force(?:-with-lease)?\b"), "force pushes are blocked"),
    (re.compile(r"\bchmod\s+-R\s+777\b"), "recursive world-writable chmod is blocked"),
    (re.compile(r"\bsudo\b"), "sudo commands are blocked"),
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "DROP TABLE statements are blocked"),
    (re.compile(r"\b(?:curl|wget)\b[^\n;&|]*\|\s*(?:sh|bash)\b"), "curl/wget piped to a shell is blocked"),
]


def _print_json(data: dict):
    print(json.dumps(data, ensure_ascii=False), end="")


def _payload(raw_payload: str) -> dict:
    try:
        return json.loads(raw_payload) if raw_payload.strip() else {}
    except json.JSONDecodeError:
        return {}


def _command_from_payload(payload: dict) -> str:
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        return tool_input.get("command") or tool_input.get("cmd") or json.dumps(tool_input)
    if isinstance(tool_input, str):
        return tool_input
    return ""


def danger_reason(command: str) -> str | None:
    """Public entry point so other Harness scripts can vet shell commands."""
    for pattern, message in DANGEROUS_RULES:
        if pattern.search(command):
            return f"{message}: {command.strip()}"
    return None


# Backwards-compatible alias for existing callers.
_danger_reason = danger_reason


def _emit_pretool_block(reason: str):
    _print_json(
        {
            "decision": "block",
            "reason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }
    )


def _emit_permission_deny(reason: str):
    _print_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny", "message": reason},
            }
        }
    )


def _emit_stop_continue():
    _print_json({"continue": True})


def _emit_stop_block(reason: str):
    _print_json({"decision": "block", "reason": reason})


def _normalize_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lstrip("./")


def _extract_paths_from_patch(patch_text: object) -> list[str]:
    if not isinstance(patch_text, str):
        return []
    paths = []
    for line in patch_text.splitlines():
        match = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+)$", line)
        if match:
            path = _normalize_path(match.group(1))
            if path:
                paths.append(path)
    return paths


def extract_paths(payload: dict) -> list[str]:
    tool_input = payload.get("tool_input", {})
    paths: list[str] = []
    if isinstance(tool_input, dict):
        for key in ("file_path", "path", "target_file", "target_path"):
            path = _normalize_path(tool_input.get(key))
            if path:
                paths.append(path)
        for key in ("files", "paths"):
            values = tool_input.get(key)
            if isinstance(values, list):
                paths.extend(path for value in values if (path := _normalize_path(value)))
        for key in ("patch", "input", "content"):
            paths.extend(_extract_paths_from_patch(tool_input.get(key)))
    elif isinstance(tool_input, str):
        paths.extend(_extract_paths_from_patch(tool_input))

    result = []
    seen = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def is_test_path(path: str) -> bool:
    lowered = path.lower()
    name = Path(path).name.lower()
    return (
        "/test/" in lowered
        or "/tests/" in lowered
        or "/__tests__/" in lowered
        or name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
        or name.endswith("test.java")
        or name.endswith("tests.java")
    )


def should_skip(path: str) -> bool:
    normalized = path.lstrip("./")
    if normalized in SKIP_NAMES:
        return True
    if normalized.startswith(SKIP_PREFIXES):
        return True
    if is_test_path(normalized):
        return True
    return Path(normalized).suffix not in SOURCE_EXTENSIONS


def _replace_prefix(path: Path, old: tuple[str, ...], new: tuple[str, ...]) -> Path | None:
    parts = path.parts
    if len(parts) < len(old) or tuple(parts[: len(old)]) != old:
        return None
    return Path(*new, *parts[len(old) :])


def candidate_tests(path: str) -> list[Path]:
    target = Path(path)
    directory = target.parent
    suffix = target.suffix
    stem = target.stem
    candidates = [
        directory / f"{stem}.test{suffix}",
        directory / f"{stem}.spec{suffix}",
        directory / "__tests__" / f"{stem}{suffix}",
        directory / "__tests__" / f"{stem}.test{suffix}",
        directory / "__tests__" / f"{stem}.spec{suffix}",
        Path("tests") / f"{stem}.test{suffix}",
        Path("tests") / f"{stem}.spec{suffix}",
    ]

    if suffix == ".py":
        candidates.extend(
            [
                directory / f"test_{stem}.py",
                directory / f"{stem}_test.py",
                Path("tests") / f"test_{stem}.py",
                Path("tests") / f"{stem}_test.py",
            ]
        )
        if target.parts and target.parts[0] == "src":
            relative = Path(*target.parts[1:])
            candidates.extend(
                [
                    Path("tests") / f"test_{relative.name}",
                    Path("tests") / relative.parent / f"test_{stem}.py",
                ]
            )

    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        candidates.extend(
            [
                Path("test") / f"{stem}.test{suffix}",
                Path("test") / f"{stem}.spec{suffix}",
                Path("tests") / f"{stem}{suffix}",
            ]
        )

    if suffix in {".java", ".kt"}:
        main_java = _replace_prefix(target, ("src", "main", "java"), ("src", "test", "java"))
        main_kotlin = _replace_prefix(target, ("src", "main", "kotlin"), ("src", "test", "kotlin"))
        for test_target in (main_java, main_kotlin):
            if test_target:
                candidates.extend(
                    [
                        test_target.with_name(f"{stem}Test{suffix}"),
                        test_target.with_name(f"{stem}Tests{suffix}"),
                    ]
                )

    return candidates


def has_matching_test(path: str, root: Path = ROOT) -> bool:
    return any((root / candidate).exists() for candidate in candidate_tests(path))


def handle_policy(mode: str, payload: dict) -> int:
    reason = _danger_reason(_command_from_payload(payload))
    if not reason:
        return 0
    if mode == "permission-request":
        _emit_permission_deny(reason)
    else:
        _emit_pretool_block(reason)
    return 0


def handle_tdd(payload: dict) -> int:
    missing = [path for path in extract_paths(payload) if not should_skip(path) and not has_matching_test(path, ROOT)]
    if not missing:
        return 0

    message = (
        "TDD Guard: implementation changes need a matching test first. "
        "Create or update tests before editing: "
        + ", ".join(missing)
    )
    if checks.guard_mode(ROOT) == "hard":
        _emit_pretool_block(message)
    else:
        print(f"WARNING: {message}", file=sys.stderr)
    return 0


def _run_check_stage(stage: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "checks.py"), "--stage", stage],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode, output


def handle_stop() -> int:
    status, output = _run_check_stage("stop")
    if status == 0 or checks.guard_mode(ROOT) != "hard":
        if status != 0 and output:
            print(f"WARNING: {output}", file=sys.stderr)
        _emit_stop_continue()
        return 0
    _emit_stop_block(output or "Project checks failed.")
    return 0


def handle_git_pre_commit() -> int:
    status, output = _run_check_stage("pre-commit")
    if status == 0:
        if output:
            print(output)
        return 0
    if output:
        print(output, file=sys.stderr)
    return status if checks.guard_mode(ROOT) == "hard" else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    mode = argv[0] if argv else ""
    payload = _payload(sys.stdin.read())

    if mode in {"pre-tool-use", "permission-request"}:
        return handle_policy(mode, payload)
    if mode == "tdd-pre-tool-use":
        return handle_tdd(payload)
    if mode == "stop":
        return handle_stop()
    if mode == "git-pre-commit":
        return handle_git_pre_commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
