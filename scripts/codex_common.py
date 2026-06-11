#!/usr/bin/env python3
"""Shared helpers for Harness scripts that invoke Codex."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ALLOWED_CODEX_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
CODEX_EXEC_TIMEOUT = 1800
CODEX_ENV_CONFIG = "shell_environment_policy.inherit=all"
ACCEPTANCE_SECTION_HEADER = "## 인수 기준"


def configure_utf8_stdio() -> None:
    """Prefer UTF-8 stdio on Windows without failing on redirected streams."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def resolve_codex_bin() -> str:
    candidates = ("codex.cmd", "codex.exe", "codex") if sys.platform == "win32" else ("codex",)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return candidates[0]


def validate_codex_effort(effort: str, *, allow_xhigh: bool = False) -> str:
    if effort not in ALLOWED_CODEX_EFFORTS:
        allowed = ", ".join(ALLOWED_CODEX_EFFORTS)
        raise ValueError(f"codex effort must be one of: {allowed}")
    if effort == "xhigh" and not allow_xhigh:
        raise ValueError("xhigh effort requires --allow-xhigh")
    return effort


def codex_effort_config(effort: str) -> list[str]:
    return ["-c", f'model_reasoning_effort="{effort}"']


def codex_base_cmd(effort: str) -> list[str]:
    return [
        resolve_codex_bin(),
        "exec",
        "--json",
        *codex_effort_config(effort),
        "-c",
        CODEX_ENV_CONFIG,
    ]


def read_acceptance_commands(step_md_path: Path) -> tuple[str, ...]:
    """Return shell commands from fenced blocks under `## 인수 기준`."""
    if not step_md_path.exists():
        return ()

    commands: list[str] = []
    in_acceptance = False
    in_code_block = False
    for raw in step_md_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            if in_acceptance:
                break
            in_acceptance = line == ACCEPTANCE_SECTION_HEADER
            continue
        if not in_acceptance:
            continue
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block and line and not line.startswith("#"):
            commands.append(line)
    return tuple(commands)
