#!/usr/bin/env python3
"""
Harness Upgrader — 템플릿 체크아웃에서 인스턴스로 harness를 동기화한다.

guides/UPGRADE.md "파일 소유 구분" 표를 그대로 코드화한다. 템플릿 소유 단위는
통째로 덮어쓰고, 프로젝트 소유 파일은 건드리지 않으며, 인스턴스
.codex/project-profile.json 의 templateVersion 만 템플릿의 TEMPLATE_VERSION 으로
갱신한다.

Usage:
    python scripts/upgrade.py --from <template-dir> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from codex_common import configure_utf8_stdio

ROOT = Path(__file__).resolve().parent.parent

# guides/UPGRADE.md "파일 소유 구분" 표의 템플릿 소유 단위. 이 목록을 바꾸면
# 같은 표와 doctor 의 REQUIRED_FILES 계약도 함께 갱신한다.
TEMPLATE_OWNED_DIRS = (
    "scripts",
    ".agents/skills/harness",
    ".agents/skills/review",
    ".githooks",
    ".codex/hooks",
)
TEMPLATE_OWNED_FILES = (
    ".codex/hooks.json",
    ".codex/config.toml",
    ".gitattributes",
    "guides/PROMPTS.md",
    "guides/CONFIGURATION.md",
    "guides/UPGRADE.md",
)
# 템플릿 전용. 인스턴스에는 복사하지 않는다(guides/UPGRADE.md 참고).
TEMPLATE_ONLY = (".github/workflows/template-ci.yml",)
PROFILE_REL = ".codex/project-profile.json"
VERSION_PATTERN = re.compile(r'TEMPLATE_VERSION\s*=\s*"([^"]+)"')


class UpgradeError(Exception):
    """업그레이드를 안전하게 진행할 수 없을 때 발생."""


def read_template_version(template_root: Path) -> str:
    """템플릿 체크아웃의 scripts/codex_common.py 에서 TEMPLATE_VERSION 을 읽는다."""
    common = template_root / "scripts" / "codex_common.py"
    if not common.is_file():
        raise UpgradeError(f"{common} not found; --from must point to a template checkout.")
    match = VERSION_PATTERN.search(common.read_text(encoding="utf-8"))
    if not match:
        raise UpgradeError("Could not find TEMPLATE_VERSION in template scripts/codex_common.py.")
    return match.group(1)


def collect_operations(template_root: Path) -> list[tuple[str, str]]:
    """덮어쓸 (kind, rel) 목록. 템플릿에 없는 단위는 건너뛴다."""
    ops: list[tuple[str, str]] = []
    for rel in TEMPLATE_OWNED_DIRS:
        if (template_root / rel).is_dir():
            ops.append(("dir", rel))
    for rel in TEMPLATE_OWNED_FILES:
        if (template_root / rel).is_file():
            ops.append(("file", rel))
    return ops


def _apply_dir(template_root: Path, instance_root: Path, rel: str) -> None:
    src = template_root / rel
    dst = instance_root / rel
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def _apply_file(template_root: Path, instance_root: Path, rel: str) -> None:
    dst = instance_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_root / rel, dst)


def apply_operations(template_root: Path, instance_root: Path, ops: list[tuple[str, str]]) -> None:
    for kind, rel in ops:
        if kind == "dir":
            _apply_dir(template_root, instance_root, rel)
        else:
            _apply_file(template_root, instance_root, rel)


def bump_template_version(instance_root: Path, version: str) -> str:
    """인스턴스 profile 의 templateVersion 만 갱신하고 이전 값을 반환한다."""
    path = instance_root / PROFILE_REL
    if not path.is_file():
        raise UpgradeError(f"{PROFILE_REL} not found; run upgrade from a project instance root.")
    profile = json.loads(path.read_text(encoding="utf-8"))
    previous = str(profile.get("templateVersion", "")).strip()
    profile["templateVersion"] = version
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return previous


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync template-owned harness units from a template checkout into this instance."
    )
    parser.add_argument(
        "--from",
        dest="template",
        required=True,
        help="Path to a fresh template checkout to upgrade from.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned changes without modifying any files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, instance_root: Path = ROOT) -> int:
    configure_utf8_stdio()
    args = _parse_args(argv)
    instance_root = instance_root.resolve()
    template_root = Path(args.template).resolve()

    try:
        if not template_root.is_dir():
            raise UpgradeError(f"--from path does not exist: {template_root}")
        if template_root == instance_root:
            raise UpgradeError("--from must point to a different checkout than this instance.")
        if not (instance_root / PROFILE_REL).is_file():
            raise UpgradeError(f"{PROFILE_REL} not found; run this from a project instance root.")
        version = read_template_version(template_root)
        ops = collect_operations(template_root)
    except UpgradeError as exc:
        print(f"upgrade blocked: {exc}")
        return 1

    current = str(json.loads((instance_root / PROFILE_REL).read_text(encoding="utf-8")).get("templateVersion", "")).strip()
    print("Harness Upgrade")
    print(f"- from: {template_root}")
    print(f"- instance: {instance_root}")
    print(f"- templateVersion: {current or 'not recorded'} -> {version}")
    print(f"- mode: {'dry-run' if args.dry_run else 'apply'}")

    print("\nTemplate-owned units to overwrite")
    for kind, rel in ops:
        print(f"- {kind}: {rel}")
    print("\nLeft untouched (project-owned): AGENTS.md, docs/, phases/, issues/, archive/,")
    print(f"  {PROFILE_REL} (templateVersion only), .codex/scope-rules.json, project skills.")
    print("Not copied (template-only): " + ", ".join(TEMPLATE_ONLY))

    if args.dry_run:
        print("\nDry run: no files changed. Re-run without --dry-run to apply.")
        return 0

    apply_operations(template_root, instance_root, ops)
    previous = bump_template_version(instance_root, version)

    print(f"\nApplied {len(ops)} unit(s). templateVersion: {previous or 'not recorded'} -> {version}")
    print("\nNext steps")
    print("1. Review contract changes in the template CHANGELOG.md between the two versions.")
    print("2. python -m pytest scripts")
    print("3. python scripts/doctor.py --instance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
