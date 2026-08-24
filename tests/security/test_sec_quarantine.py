"""Stage C — size-capped quarantine for deletions (G-11).

Move-first deletions with restore/purge, bilingual refusals, and bounds
that fail closed: an oversized item or a full store is refused, never
silently destroyed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import dream.security.quarantine as quarantine
from dream.security.quarantine import (
    QuarantineError,
    list_quarantine,
    purge,
    quarantine_delete,
    restore,
)


@pytest.fixture(autouse=True)
def _quarantine_root(tmp_path, monkeypatch):
    monkeypatch.setenv(quarantine.QUARANTINE_DIR_ENV, str(tmp_path / "quarantine"))
    return tmp_path / "quarantine"


def test_delete_moves_the_file_and_records_metadata(tmp_path: Path, _quarantine_root) -> None:
    target = tmp_path / "victim.txt"
    target.write_text("precious bytes", encoding="utf-8")
    entry = quarantine_delete(target)
    assert not target.exists()
    assert entry["size_bytes"] == len("precious bytes")
    assert entry["is_dir"] is False
    rows = list_quarantine()
    assert rows and rows[0]["id"] == entry["id"]
    # the bytes survive inside the quarantine
    held = _quarantine_root / entry["id"] / "victim.txt"
    assert held.read_text(encoding="utf-8") == "precious bytes"


def test_delete_moves_whole_directories(tmp_path: Path, _quarantine_root) -> None:
    tree = tmp_path / "skill-folder"
    (tree / "references").mkdir(parents=True)
    (tree / "SKILL.md").write_text("body", encoding="utf-8")
    (tree / "references" / "soil.md").write_text("soil", encoding="utf-8")
    entry = quarantine_delete(tree)
    assert entry["is_dir"] is True
    assert not tree.exists()
    held = _quarantine_root / entry["id"] / "skill-folder"
    assert (held / "references" / "soil.md").read_text(encoding="utf-8") == "soil"


def test_restore_returns_the_item_byte_identical(tmp_path: Path) -> None:
    target = tmp_path / "notes" / "restore-me.txt"
    target.parent.mkdir(parents=True)
    target.write_text("round trip", encoding="utf-8")
    entry = quarantine_delete(target)
    meta = restore(entry["id"])
    assert target.read_text(encoding="utf-8") == "round trip"
    assert meta["id"] == entry["id"]
    assert list_quarantine() == []


def test_restore_refuses_when_the_original_is_occupied(tmp_path: Path, _quarantine_root) -> None:
    target = tmp_path / "busy.txt"
    target.write_text("v1", encoding="utf-8")
    entry = quarantine_delete(target)
    target.write_text("v2-taken", encoding="utf-8")
    with pytest.raises(QuarantineError) as exc:
        restore(entry["id"])
    assert "occupied" in str(exc.value)
    assert "\u0627\u0634\u063a\u0627\u0644" in str(exc.value)  # bilingual
    assert target.read_text(encoding="utf-8") == "v2-taken"
    # the quarantined copy is still safe
    assert (_quarantine_root / entry["id"] / "busy.txt").exists()


def test_purge_destroys_only_the_quarantined_copy(tmp_path: Path, _quarantine_root) -> None:
    target = tmp_path / "gone.txt"
    target.write_text("x", encoding="utf-8")
    entry = quarantine_delete(target)
    purge(entry["id"])
    assert list_quarantine() == []
    assert not (_quarantine_root / entry["id"]).exists()
    assert not target.exists()  # purge never resurrects


def test_missing_path_is_refused_bilingually(tmp_path: Path) -> None:
    with pytest.raises(QuarantineError) as exc:
        quarantine_delete(tmp_path / "nothing-here")
    assert "nothing exists" in str(exc.value)
    assert "\u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f" in str(exc.value)


def test_oversized_items_are_refused_not_destroyed(tmp_path: Path) -> None:
    target = tmp_path / "big.bin"
    target.write_bytes(b"x" * 4096)
    with pytest.raises(QuarantineError) as exc:
        quarantine_delete(target, max_item_bytes=1024)
    assert "larger than the quarantine cap" in str(exc.value)
    assert target.exists() and target.stat().st_size == 4096


def test_a_full_store_refuses_new_deletions(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    first.write_bytes(b"a" * 2048)
    quarantine_delete(first, max_total_bytes=10_000)
    second = tmp_path / "b.txt"
    second.write_bytes(b"b" * 2048)
    with pytest.raises(QuarantineError) as exc:
        quarantine_delete(second, max_total_bytes=3000)
    assert "full" in str(exc.value)
    assert second.exists()


def test_delete_skill_routes_through_the_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dream.tools as tools

    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", workspace.resolve())
    monkeypatch.setenv("DREAM_SKILLS_DB", str(tmp_path / "ledger.db"))
    import dream.skills as skills

    skills.save_skill_md("quarantine-probe", "when testing", "body text")
    result = skills.delete_skill("quarantine-probe")
    assert result["deleted"] is True
    assert result["quarantined"] is True
    assert not (workspace / "skills" / "quarantine-probe").exists()
    # the entry is restorable through the quarantine API
    rows = [row for row in list_quarantine() if row["id"] == result["quarantine_id"]]
    assert rows and rows[0]["is_dir"] is True
    restore(result["quarantine_id"])
    assert (workspace / "skills" / "quarantine-probe" / "SKILL.md").exists()


def test_quarantine_entries_are_newest_first(tmp_path: Path) -> None:
    import time

    for index in range(3):
        item = tmp_path / f"item-{index}.txt"
        item.write_text(str(index), encoding="utf-8")
        quarantine_delete(item)
        time.sleep(0.02)  # distinct timestamps make the ordering observable
    rows = list_quarantine()
    assert [row["name"] for row in rows] == ["item-2.txt", "item-1.txt", "item-0.txt"]


def test_unknown_ids_are_refused() -> None:
    with pytest.raises(QuarantineError):
        restore("q_doesnotexist")
    with pytest.raises(QuarantineError):
        purge("q_doesnotexist")
