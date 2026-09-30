"""Check that a fixed source tree has exactly one distribution decision per file."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "DISTRIBUTION_MANIFEST.json"
ACTIONS = {"include", "exclude", "transform"}
OWNERS = {"template", "template-repository", "new-project"}


def tracked_paths(commit: str, root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", commit],
        cwd=root, capture_output=True, check=True,
    )
    return [name.decode("utf-8") for name in result.stdout.split(b"\0") if name]


def audit(manifest: dict, paths: list[str]) -> tuple[list[str], Counter]:
    errors: list[str] = []
    counts: Counter = Counter()
    rules = manifest["rules"]
    for number, rule in enumerate(rules, 1):
        if rule.get("action") not in ACTIONS or rule.get("owner") not in OWNERS:
            errors.append(f"rule {number}: invalid action or owner")
        if not rule.get("reason"):
            errors.append(f"rule {number}: missing reason")
        if not any(fnmatch.fnmatchcase(path, rule["pattern"]) for path in paths):
            errors.append(f"rule {number}: pattern matches no source file: {rule['pattern']}")
    for path in paths:
        matches = [rule for rule in rules if fnmatch.fnmatchcase(path, rule["pattern"])]
        if len(matches) != 1:
            errors.append(f"{path}: matched {len(matches)} rules")
        else:
            counts[matches[0]["action"]] += 1
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--check-ref", action="store_true", help="also require sourceRef to equal sourceCommit")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    commit = manifest["sourceCommit"]
    paths = tracked_paths(commit)
    errors, counts = audit(manifest, paths)
    if args.check_ref:
        resolved = subprocess.run(
            ["git", "rev-parse", manifest["sourceRef"]], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if resolved != commit:
            errors.append(f"{manifest['sourceRef']} moved: {resolved} != {commit}")
    for error in errors:
        print(error)
    print(f"source={commit} files={len(paths)} include={counts['include']} "
          f"exclude={counts['exclude']} transform={counts['transform']}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
