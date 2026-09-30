#!/usr/bin/env python3
"""Check deterministic documentation contracts and repair missing ADR index entries."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SCRIPT = re.compile(r"\b(?:python|python3)\s+(scripts/[\w./-]+\.py)\b")
ADR = re.compile(r"^#\s+(ADR-\d{4}):\s*(.+?)\s*$", re.MULTILINE)
INDEX_ENTRY = re.compile(r"^\s*-\s+\[ADR-\d{4}:[^\]]+\]\(adr/[^)]+\)\s*$", re.MULTILINE)
TEXT_FILES = ("README.md", "docs", "guides")


def _markdown_files(root: Path):
    for item in TEXT_FILES:
        path = root / item
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(path.rglob("*.md"))


def _problems(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in _markdown_files(root):
        relative = path.relative_to(root).as_posix()
        fenced = False
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for match in LINK.finditer(line):
                target = match.group(1).split(' "', 1)[0].strip("<>")
                if not target or target.startswith("#") or urlsplit(target).scheme:
                    continue
                target_path = unquote(target.split("#", 1)[0].split("?", 1)[0])
                if target_path and not (path.parent / target_path).exists():
                    findings.append({"path": relative, "line": str(line_no),
                                     "kind": "broken-link", "target": target})

    for path in (root / "docs" / "COMMANDS.md", root / "docs" / "ARCHITECTURE.md"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in SCRIPT.finditer(line):
                if not (root / match.group(1)).is_file():
                    findings.append({"path": relative, "line": str(line_no),
                                     "kind": "missing-script", "target": match.group(1)})
    return findings


def audit(root: Path, *, fix_safe: bool = False) -> dict[str, list]:
    root = root.resolve()
    index = root / "docs" / "ADR.md"
    adr_dir = root / "docs" / "adr"
    if not index.is_file() or not adr_dir.is_dir():
        raise ValueError("docs/ADR.md and docs/adr/ are required")
    original = index.read_text(encoding="utf-8")
    indexed = {
        unquote(target)
        for line in original.splitlines()
        if INDEX_ENTRY.match(line)
        for target in re.findall(r"\]\((adr/[^)]+)\)", line)
    }
    missing: list[tuple[str, str]] = []
    findings = _problems(root)
    for adr in sorted(adr_dir.glob("*.md")):
        relative = f"adr/{adr.name}"
        if relative in indexed:
            continue
        title = ADR.search(adr.read_text(encoding="utf-8"))
        if not title or not adr.name.startswith(title.group(1).split("-")[1] + "-"):
            findings.append({"path": adr.relative_to(root).as_posix(), "line": "1",
                             "kind": "adr-title", "target": "ADR-0000: title"})
        else:
            missing.append((relative, f"- [{title.group(1)}: {title.group(2)}]({relative})"))

    changes: list[str] = []
    if missing and fix_safe:
        if "## ADR 목록" not in original:
            findings.append({"path": "docs/ADR.md", "line": "1",
                             "kind": "adr-index-section", "target": "## ADR 목록"})
        else:
            lines = original.splitlines(keepends=True)
            entries = [i for i, line in enumerate(lines) if INDEX_ENTRY.match(line)]
            if entries:
                insertion = entries[-1] + 1
            else:
                insertion = next(i for i, line in enumerate(lines)
                                 if line.strip() == "## ADR 목록") + 1
            lines[insertion:insertion] = [entry + "\n" for _, entry in missing]
            index.write_text("".join(lines), encoding="utf-8")
            changes = [relative for relative, _ in missing]
    elif missing:
        findings.extend({"path": "docs/ADR.md", "line": "1", "kind": "adr-index-missing",
                         "target": relative} for relative, _ in missing)

    if changes:
        findings = [item for item in findings if not (
            item["path"] == "docs/ADR.md" and item["kind"] == "broken-link"
        )]
        findings.extend(item for item in _problems(root) if item["path"] == "docs/ADR.md")
    return {"safeChanges": changes, "needsJudgment": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fix-safe", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(args.root, fix_safe=args.fix_safe)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"gardening audit failed: {exc}\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"safe changes: {len(result['safeChanges'])}, "
              f"needs judgment: {len(result['needsJudgment'])}")
        for finding in result["needsJudgment"]:
            print(f"{finding['path']}:{finding['line']}: "
                  f"{finding['kind']}: {finding['target']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
