#!/usr/bin/env sh
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$repo_root/.codex/hooks/tdd-guard.py" "${1:-}"
fi

if command -v python >/dev/null 2>&1; then
  exec python "$repo_root/.codex/hooks/tdd-guard.py" "${1:-}"
fi

if command -v py >/dev/null 2>&1; then
  exec py -3 "$repo_root/.codex/hooks/tdd-guard.py" "${1:-}"
fi

echo "Python 3 is required to run Codex guard hooks." >&2
exit 1
