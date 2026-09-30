from pathlib import Path

import garden_docs


def _repo(root: Path):
    (root / "docs" / "adr").mkdir(parents=True)
    (root / "docs" / "ADR.md").write_text(
        "# ADR\n\n## ADR 목록\n- [ADR-0001: Existing](adr/0001-existing.md)\n",
        encoding="utf-8",
    )
    (root / "docs" / "adr" / "0001-existing.md").write_text(
        "# ADR-0001: Existing\n", encoding="utf-8"
    )


def test_adr_fix_only_adds_missing_entry_and_is_idempotent(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "adr" / "0002-new.md").write_text(
        "# ADR-0002: New decision\n", encoding="utf-8"
    )
    before = (tmp_path / "docs" / "ADR.md").read_text(encoding="utf-8")
    report = garden_docs.audit(tmp_path)
    assert report["safeChanges"] == []
    assert report["needsJudgment"] == [
        {"path": "docs/ADR.md", "line": "1", "kind": "adr-index-missing", "target": "adr/0002-new.md"}
    ]
    assert (tmp_path / "docs" / "ADR.md").read_text(encoding="utf-8") == before

    report = garden_docs.audit(tmp_path, fix_safe=True)
    assert report == {"safeChanges": ["adr/0002-new.md"], "needsJudgment": []}
    assert garden_docs.audit(tmp_path, fix_safe=True) == {"safeChanges": [], "needsJudgment": []}
    assert "[ADR-0002: New decision](adr/0002-new.md)" in (
        tmp_path / "docs" / "ADR.md"
    ).read_text(encoding="utf-8")


def test_broken_link_and_command_need_judgment(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "COMMANDS.md").write_text(
        "[missing](gone.md)\n`python scripts/removed.py`\n"
        "[external](https://example.com/x) [anchor](#section)\n",
        encoding="utf-8",
    )
    report = garden_docs.audit(tmp_path, fix_safe=True)
    assert report["safeChanges"] == []
    assert {(item["kind"], item["target"]) for item in report["needsJudgment"]} == {
        ("broken-link", "gone.md"),
        ("missing-script", "scripts/removed.py"),
    }


def test_ambiguous_adr_title_is_never_auto_fixed(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "adr" / "0002-new.md").write_text(
        "# A decision without a number\n", encoding="utf-8"
    )
    report = garden_docs.audit(tmp_path, fix_safe=True)
    assert report["safeChanges"] == []
    assert any(item["kind"] == "adr-title" for item in report["needsJudgment"])


def test_adr_number_mismatch_is_not_inserted(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "adr" / "0002-new.md").write_text(
        "# ADR-0003: Different number\n", encoding="utf-8"
    )
    report = garden_docs.audit(tmp_path, fix_safe=True)
    assert report["safeChanges"] == []
    assert any(item["kind"] == "adr-title" for item in report["needsJudgment"])
