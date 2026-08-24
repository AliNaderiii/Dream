"""Stage B — durable approval history (L2, SEC-G-07).

Append-only, env-overridable, fail-closed on corruption (never silently
wiped), and loud rather than fatal when an append fails mid-turn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dream.security.history import (
    APPROVAL_DB_ENV,
    DEFAULT_APPROVAL_DB,
    ApprovalHistory,
    ApprovalStoreError,
)


def _row(store: ApprovalHistory, index: int = 0) -> dict:
    return store.entries()[index]


def test_records_round_trip(tmp_path: Path) -> None:
    store = ApprovalHistory(str(tmp_path / "a.db"))
    ok = store.record(
        verdict="approved_human",
        tool="run_shell",
        command="echo hi",
        mode="manual",
        context="interactive",
        detail="test",
    )
    assert ok
    row = _row(store)
    assert row["verdict"] == "approved_human"
    assert row["command"] == "echo hi"
    assert row["mode"] == "manual"
    assert row["context"] == "interactive"
    assert row["detail"] == "test"
    assert row["id"] >= 1 and row["ts"] > 0


def test_entries_are_newest_first_and_paginate(tmp_path: Path) -> None:
    store = ApprovalHistory(str(tmp_path / "a.db"))
    for i in range(5):
        store.record(
            verdict=f"v{i}", tool="run_shell", command=f"c{i}", mode="manual"
        )
    rows = store.entries()
    assert [row["verdict"] for row in rows] == ["v4", "v3", "v2", "v1", "v0"]
    assert [row["verdict"] for row in store.entries(limit=2)] == ["v4", "v3"]
    assert [row["verdict"] for row in store.entries(limit=2, offset=3)] == ["v1", "v0"]
    assert store.count() == 5


def test_env_override_names_the_store(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.db"
    monkeypatch.setenv(APPROVAL_DB_ENV, str(target))
    store = ApprovalHistory()
    assert store.path == str(target)
    store.record(verdict="floor_blocked", tool="run_shell", command="x", mode="manual")
    assert target.exists()


def test_default_path_constant_is_stable() -> None:
    assert DEFAULT_APPROVAL_DB == "data/dream-approvals.db"
    assert APPROVAL_DB_ENV == "DREAM_APPROVAL_DB"


def test_reopen_survives_and_never_duplicates(tmp_path: Path) -> None:
    path = str(tmp_path / "a.db")
    first = ApprovalHistory(path)
    first.record(verdict="approved_human", tool="t", command="c", mode="manual")
    first.close()
    second = ApprovalHistory(path)
    second.record(verdict="denied_by_approver", tool="t", command="c", mode="manual")
    assert second.count() == 2


def test_corrupt_file_fails_closed_with_a_bilingual_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.db"
    before = b"this is not sqlite, just noise for the fail-closed path"
    broken.write_bytes(before)
    with pytest.raises(ApprovalStoreError) as exc:
        ApprovalHistory(str(broken))
    message = str(exc.value)
    assert "unreadable" in message
    fa_fragment = "\u063a\u06cc\u0631\u0642\u0627\u0628\u0644 \u062e\u0648\u0627\u0646\u062f\u0646"
    assert fa_fragment in message
    # Corruption is never silently wiped: the file stays byte-identical.
    assert broken.read_bytes() == before


def test_corruption_mid_life_refuses_reads_and_keeps_the_bytes(tmp_path: Path) -> None:
    path = tmp_path / "a.db"
    store = ApprovalHistory(str(path))
    store.record(verdict="approved_human", tool="t", command="c", mode="manual")
    store.close()
    path.write_bytes(b"\x00garbage\x01")
    before = path.read_bytes()
    reopened = ApprovalHistory.__new__(ApprovalHistory)
    # Rebuild the object without the constructor to simulate a store that
    # breaks between open and read: mark broken and verify fail-closed reads.
    import threading

    reopened.path = str(path)
    reopened._lock = threading.RLock()
    reopened._broken = True
    with pytest.raises(ApprovalStoreError):
        reopened.entries()
    with pytest.raises(ApprovalStoreError):
        reopened.count()
    assert reopened.record(verdict="x", tool="t", command="c", mode="m") is False
    assert path.read_bytes() == before


def test_module_is_append_only_by_construction() -> None:
    source = Path("dream/security/history.py").read_text(encoding="utf-8")
    assert "UPDATE " not in source
    assert "DELETE FROM" not in source
    assert "DROP TABLE" not in source


def test_limit_is_clamped(tmp_path: Path) -> None:
    store = ApprovalHistory(str(tmp_path / "a.db"))
    store.record(verdict="v", tool="t", command="c", mode="m")
    assert store.entries(limit=10_000)  # clamped, not an error
    assert store.entries(limit=0)
