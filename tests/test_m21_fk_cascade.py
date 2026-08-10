"""Pins M21: the store cascades reminder deletion to its delivery rows.

The delivery table ``reminder_deliveries`` references ``reminders(id)`` with no
``ON DELETE CASCADE``, and the store turns foreign key enforcement on. So a
reminder that has already fired — and therefore owns delivery rows — cannot be
deleted at all: ``store.delete_reminder`` raises ``IntegrityError: FOREIGN KEY
constraint failed`` and the row survives. Measured on merged trunk with the
real store class (reproduced in this file's module docstring steps).

The fix belongs under the store: add the cascade. A schema-only change fixes
nothing on the owner's existing database (the ``CREATE TABLE`` is guarded by
``IF NOT EXISTS`` and is silently skipped when the table is already there), so
this milestone ships a migration that rebuilds the existing table: read the
stored schema text, and if the cascade is absent, create the new table, copy
every row, drop the old one, rename the new one into place. The migration is
idempotent (a second open changes nothing) and preserves every delivery row,
counted before and after.

What done looks like, each pinned here:

- a fired reminder can be deleted through the store, no hand cleanup
- the terminal ``/unremind`` command deletes a fired reminder and says so
- an old database without the cascade gains it on open (schema text read back)
- delivery rows are preserved across the migration, counted before and after
- ``PRAGMA foreign_key_check`` is clean after the rebuild
- opening the same file twice is a no-op the second time
- deleting one reminder leaves another's delivery rows alone
- the workaround in the agent's ``cancel_reminder`` is removed; conversation
  cancellation still works
"""

from __future__ import annotations

import json

from cli import dispatch_command
from dream import tools
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore
from dream.reminders import parse_date_to_timestamp

# ---------------------------------------------------------------------------
# Persian literals as backslash-u escapes, with glosses.
# ---------------------------------------------------------------------------

_T_BILL = "\u0642\u0628\u0636 \u0628\u0631\u0642"  # قبض برق
_T_LOAN = "\u0642\u0633\u0637 \u0648\u0627\u0645"  # قسط وام


def _delivery_count(store, reminder_id):
    return store.conn.execute(
        "SELECT COUNT(*) FROM reminder_deliveries WHERE reminder_id = ?",
        (reminder_id,),
    ).fetchone()[0]


def _schema_text(store):
    return store.conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='reminder_deliveries'"
    ).fetchone()[0]


def _simulate_old_database(store):
    """Rebuild reminder_deliveries without CASCADE to mimic a database created
    before this milestone. Delivery rows are preserved so the migration's row
    copy can be verified against this exact set."""
    rows = list(
        store.conn.execute(
            "SELECT reminder_id, destination, fired_at, delivered_at "
            "FROM reminder_deliveries"
        ).fetchall()
    )
    store.conn.execute("DROP TABLE reminder_deliveries")
    store.conn.execute(
        """CREATE TABLE reminder_deliveries (
            reminder_id INTEGER NOT NULL, destination TEXT NOT NULL,
            fired_at REAL NOT NULL, delivered_at REAL NOT NULL,
            PRIMARY KEY (reminder_id, destination, fired_at),
            FOREIGN KEY (reminder_id) REFERENCES reminders(id)
        )"""
    )
    store.conn.executemany(
        "INSERT INTO reminder_deliveries "
        "(reminder_id, destination, fired_at, delivered_at) VALUES (?, ?, ?, ?)",
        rows,
    )
    store.conn.commit()
    assert "ON DELETE CASCADE" not in _schema_text(store).upper()


# ---------------------------------------------------------------------------
# 1. A fired reminder can be deleted through the store, with no hand cleanup.
# ---------------------------------------------------------------------------


def test_fired_reminder_can_be_deleted_through_store(tmp_path):
    with MemoryStore(str(tmp_path / "del.db")) as store:
        fired = store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1
        )
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        assert _delivery_count(store, fired.id) == 1, "the fire must record a delivery"
        # Before the fix this raises IntegrityError and the row survives.
        assert store.delete_reminder(fired.id) is True, "delete must succeed through the store"
        assert store.list_reminders(include_inactive=True) == [], "the parent row must be gone"
        assert _delivery_count(store, fired.id) == 0, "delivery rows must not outlive the reminder"
        print(f"[store-delete] fired reminder {fired.id} deleted; deliveries 1 -> 0")


# ---------------------------------------------------------------------------
# 2. The terminal /unremind command deletes a fired reminder and says so.
# ---------------------------------------------------------------------------


def test_terminal_unremind_deletes_fired_reminder(tmp_path):
    with MemoryStore(str(tmp_path / "cli.db")) as store:
        fired = store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1
        )
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        assert _delivery_count(store, fired.id) == 1
        dream = Dream(store, EchoBackend())
        out: list[str] = []
        dispatch_command(f"/unremind {fired.id}", dream, out.append)
        assert out, "the command must produce output"
        assert "deleted" in out[0].lower() or "permanently" in out[0].lower(), (
            f"the command must say it deleted, got {out[0]!r}"
        )
        assert store.list_reminders(include_inactive=True) == [], "the row must be gone"
        assert _delivery_count(store, fired.id) == 0, "deliveries must be cascaded"
        print(f"[terminal-unremind] {out[0]!r}")


# ---------------------------------------------------------------------------
# 3. An old database without the cascade gains it on open (schema text read back).
# ---------------------------------------------------------------------------


def test_old_database_gains_cascade_on_open(tmp_path):
    db = str(tmp_path / "old.db")
    with MemoryStore(db) as store:
        fired = store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1
        )
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        before_children = _delivery_count(store, fired.id)
        assert before_children == 1
        # Rewind the table to the pre-migration shape (no cascade), same rows.
        _simulate_old_database(store)
        assert "ON DELETE CASCADE" not in _schema_text(store).upper()

    # Reopen: the store must migrate the existing table to carry the cascade.
    with MemoryStore(db) as store:
        schema = _schema_text(store)
        assert "ON DELETE CASCADE" in schema.upper(), (
            f"old database must gain the cascade on open, got schema: {schema}"
        )
        assert _delivery_count(store, fired.id) == before_children, "rows must survive the rebuild"
        # And the cascade must actually work now.
        assert store.delete_reminder(fired.id) is True
        assert _delivery_count(store, fired.id) == 0
        print(f"[old-db] cascade gained on open; deliveries {before_children} -> 0 after delete")


# ---------------------------------------------------------------------------
# 4. Delivery rows are preserved across the migration, counted before/after.
# ---------------------------------------------------------------------------


def test_rows_preserved_across_migration_counted(tmp_path):
    db = str(tmp_path / "rows.db")
    with MemoryStore(db) as store:
        a = store.add_reminder(_T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1)
        b = store.add_reminder(_T_LOAN, parse_date_to_timestamp("1405-04-20"), repeat_months=1)
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="telegram"
        )
        before = {a.id: _delivery_count(store, a.id), b.id: _delivery_count(store, b.id)}
        assert before == {a.id: 2, b.id: 2}, f"two destinations each, got {before}"
        _simulate_old_database(store)

    with MemoryStore(db) as store:
        assert "ON DELETE CASCADE" in _schema_text(store).upper()
        after = {a.id: _delivery_count(store, a.id), b.id: _delivery_count(store, b.id)}
        assert after == before, f"rows must be preserved exactly: before={before} after={after}"
        print(f"[rows-preserved] before={before} after={after}")


# ---------------------------------------------------------------------------
# 5. Opening the same file twice is a no-op the second time.
# ---------------------------------------------------------------------------


def test_opening_twice_is_noop(tmp_path):
    db = str(tmp_path / "twice.db")
    with MemoryStore(db) as store:
        fired = store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1
        )
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        _simulate_old_database(store)
        count_after_sim = _delivery_count(store, fired.id)

    # First open runs the migration.
    with MemoryStore(db) as store:
        assert "ON DELETE CASCADE" in _schema_text(store).upper()
        # Second open on the already-migrated file changes nothing.
        with MemoryStore(db) as store2:
            assert _schema_text(store2) == _schema_text(store), (
                "a second open must not alter the schema"
            )
            assert _delivery_count(store2, fired.id) == count_after_sim
            # The table was not dropped/recreated out from under the first handle:
            assert _delivery_count(store, fired.id) == count_after_sim
        print("[noop-twice] second open left schema and row counts unchanged")


# ---------------------------------------------------------------------------
# 6. Deleting one reminder leaves another's delivery rows alone.
# ---------------------------------------------------------------------------


def test_one_reminders_deletion_leaves_anothers_deliveries_alone(tmp_path):
    with MemoryStore(str(tmp_path / "isolation.db")) as store:
        a = store.add_reminder(_T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1)
        b = store.add_reminder(_T_LOAN, parse_date_to_timestamp("1405-04-20"), repeat_months=1)
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        assert _delivery_count(store, a.id) == 1 and _delivery_count(store, b.id) == 1
        assert store.delete_reminder(a.id) is True
        assert _delivery_count(store, a.id) == 0, "the deleted reminder's deliveries go"
        assert _delivery_count(store, b.id) == 1, "the other reminder's deliveries stay"
        assert store.list_reminders(include_inactive=True)[0].id == b.id
        print("[isolation] deleting one reminder left the other's delivery row intact")


# ---------------------------------------------------------------------------
# 7. PRAGMA foreign_key_check is clean after the rebuild.
# ---------------------------------------------------------------------------


def test_foreign_key_check_clean_after_migration(tmp_path):
    db = str(tmp_path / "fkcheck.db")
    with MemoryStore(db) as store:
        a = store.add_reminder(_T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1)
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        _simulate_old_database(store)

    with MemoryStore(db) as store:
        violations = store.conn.execute("PRAGMA foreign_key_check").fetchall()
        assert violations == [], f"foreign_key_check must be clean, got {violations}"
        # And the rebuilt table's FK is real: deleting the parent cascades.
        store.delete_reminder(a.id)
        violations2 = store.conn.execute("PRAGMA foreign_key_check").fetchall()
        assert violations2 == [], f"no dangling FK after delete, got {violations2}"
        print("[fk-check] clean before and after cascaded delete")


# ---------------------------------------------------------------------------
# 8. The agent workaround is removed; conversation cancellation still works.
# ---------------------------------------------------------------------------


def test_conversational_cancel_still_works_after_workaround_removed(tmp_path):
    with MemoryStore(str(tmp_path / "conv.db")) as store:
        fired = store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1
        )
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        assert _delivery_count(store, fired.id) == 1
        Dream(store, EchoBackend())
        arguments = {"text": _T_BILL}
        payload = json.loads(tools.execute("cancel_reminder", arguments))
        assert payload["status"] == "ok", f"conversational cancel must succeed, got {payload!r}"
        result = payload["result"]
        assert result["id"] == fired.id
        assert _delivery_count(store, fired.id) == 0, "deliveries must go with the parent"
        assert store.list_reminders(include_inactive=True) == []
        assert result["due"] in result["message"], "the confirmation names its Jalali date"
        print(f"[conv-cancel] {result['message']}")


def test_cancel_reminder_workaround_block_removed_from_agent():
    """The agent's cancel_reminder must no longer hand-delete delivery rows;
    the store cascade owns that now. We assert the workaround code is gone by
    inspecting the source of the cancel tool's body."""
    import inspect

    from dream import agent as agent_module

    # Find the cancel_reminder tool function registered by Dream.
    src = inspect.getsource(agent_module.Dream._register_reminder_tools)
    assert "reminder_deliveries" not in src, (
        "the agent workaround that hand-deletes reminder_deliveries must be "
        "removed; the store cascade now owns child removal"
    )
    assert "DELETE FROM reminder" not in src, (
        "the agent must not issue a raw DELETE against reminder_deliveries"
    )
    print("[workaround-removed] agent no longer hand-deletes delivery rows")


# ---------------------------------------------------------------------------
# 9. Trap two proof: the pragma read-back at each step.
# ---------------------------------------------------------------------------


def test_pragma_readback_proves_switch_order():
    """Trap two: ``PRAGMA foreign_keys`` set inside a transaction is silently
    ignored. The migration therefore sets it outside the transaction and reads
    it back to prove the switch took effect. This test pastes the read-back
    values the brief asks for."""
    with MemoryStore(":memory:") as store:
        con = store.conn
        # Baseline: the store turns enforcement on at construction.
        val = con.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"\n[pragma] baseline foreign_keys = {val}")
        assert val == 1, "store must open with foreign_keys ON"

        # Outside a transaction the switch works both ways.
        con.execute("PRAGMA foreign_keys = OFF")
        val_outside_off = con.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"[pragma] outside txn, after OFF -> read back = {val_outside_off}")
        assert val_outside_off == 0, "OFF outside a transaction must read back 0"

        con.execute("PRAGMA foreign_keys = ON")
        val_outside_on = con.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"[pragma] outside txn, after ON  -> read back = {val_outside_on}")
        assert val_outside_on == 1, "ON outside a transaction must read back 1"

        # Inside a transaction the switch is silently ignored (trap two).
        con.execute("BEGIN")
        con.execute("PRAGMA foreign_keys = OFF")
        val_inside = con.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"[pragma] inside txn,  after OFF -> read back = {val_inside} (ignored)")
        assert val_inside == 1, (
            "OFF inside a transaction is silently ignored -> still 1 (trap two)"
        )
        con.execute("COMMIT")
        val_after_commit = con.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"[pragma] after commit            -> read back = {val_after_commit}")
        assert val_after_commit == 1, "enforcement restored after commit"
