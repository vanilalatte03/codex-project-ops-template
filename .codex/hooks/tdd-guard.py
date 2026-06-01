#!/usr/bin/env python3
"""Cross-platform entrypoint for Codex and Git guard hooks."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path(__file__).resolve().parents[2]


def main() -> int:
    root = _repo_root()
    guard_path = root / "scripts" / "guard.py"
    if not guard_path.exists():
        print(f"guard.py not found: {guard_path}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(root / "scripts"))
    sys.argv = [str(guard_path), *sys.argv[1:]]
    runpy.run_path(str(guard_path), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
