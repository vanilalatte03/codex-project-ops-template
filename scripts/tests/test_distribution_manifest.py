import json
import subprocess

import pytest
import verify_distribution_manifest as distribution


def test_fixed_source_tree_is_classified_once():
    manifest = json.loads(distribution.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    try:
        paths = distribution.tracked_paths(manifest["sourceCommit"])
    except subprocess.CalledProcessError:
        pytest.skip("fixed source commit is absent from the shallow CI checkout")

    errors, counts = distribution.audit(manifest, paths)

    assert errors == []
    assert sum(counts.values()) == len(paths)


def test_audit_fails_on_overlap_and_uncovered_path():
    manifest = {
        "rules": [
            {"pattern": "docs/**", "action": "include", "owner": "template", "reason": "shared"},
            {"pattern": "docs/PRD.md", "action": "transform", "owner": "new-project", "reason": "reset"},
        ]
    }

    errors, counts = distribution.audit(manifest, ["docs/PRD.md", "README.md"])

    assert "docs/PRD.md: matched 2 rules" in errors
    assert "README.md: matched 0 rules" in errors
    assert sum(counts.values()) == 0
