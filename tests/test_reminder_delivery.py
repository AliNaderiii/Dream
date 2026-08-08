"""Pin per-destination reminder delivery, the feature M6 shipped with no tests.

M6 added two tables — ``reminder_deliveries`` and ``reminder_destinations`` —
and a ``destination`` argument on the due check, so each notification target
(a terminal, a paired Telegram chat) receives each due reminder exactly once
and independently of the others. The milestone shipped green at 490 passing
tests, exactly the count before it: nothing new was covered. Two new tables,
a new argument, and the whole delivery rule had no test at all, so any future
change could break them silently while the suite stayed green.

These tests pin the behaviours measured working on a fresh clone:

- two destinations each receive the same due reminder exactly once;
- a one-off still reaches a second destination after the first consumed it and
  the row went inactive — the defect M6 existed to fix;
- a repeating reminder advances exactly one period no matter how many
  destinations read it (about thirty days for a monthly reminder, not sixty);
- the default destination behaves exactly as before for a lone terminal;
- a destination the store has never seen receives every currently-overdue
  reminder at once (pinned as-is; see the pull request for whether that is the
  right behaviour); and
- a database created by the previous release opens, gains the two new delivery
  tables in place, and keeps its data.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from dream.memory import MemoryStore
from dream.reminders import advance_due_date

# The schema as the previous release left it: memories and reminders tables,
# but neither of the two delivery tables M6 added. Opening this file with the
# current store must add the two tables and leave the existing rows in place.
_PREVIOUS_RELEASE_SCHEMA = """
CREATE TABLE memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL DEFAULT 'local',
    kind         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    norm         TEXT    NOT NULL,
    tags         TEXT    NOT NULL DEFAULT '[]',
    importance   REAL    NOT NULL DEFAULT 0.5,
    created_at   REAL    NOT NULL,
    last_used_at REAL    NOT NULL,
    use_count      INTEGER NOT NULL DEFAULT 0,
    source         TEXT    NOT NULL DEFAULT '',
    archived       INTEGER NOT NULL DEFAULT 0,
    superseded_by  INTEGER,
    pinned         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE reminders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT    NOT NULL DEFAULT 'local',
    text           TEXT    NOT NULL,
    due_at         REAL    NOT NULL,
    next_due       REAL    NOT NULL,
    repeat_days    INTEGER,
    repeat_months  INTEGER,
    last_fired_at  REAL,
    created_at     REAL    NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1,
    anchor_day     INTEGER
);
"""


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "delivery.db"))
    yield s
    s.close()


def _table_names(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def test_each_destination_receives_each_due_reminder_exactly_once(store):
    # Measured: terminal received 2, telegram received 2, then a second call
    # to either destination returns nothing.
    now = time.time()
    store.add_reminder("alpha", now - 10)
    store.add_reminder("beta", now - 10)

    terminal_first = store.check_due_reminders(now=now, destination="terminal")
    telegram_first = store.check_due_reminders(now=now, destination="telegram")

    assert {r.text for r in terminal_first} == {"alpha", "beta"}
    assert {r.text for r in telegram_first} == {"alpha", "beta"}

    terminal_second = store.check_due_reminders(now=now, destination="terminal")
    telegram_second = store.check_due_reminders(now=now, destination="telegram")

    assert terminal_second == []
    assert telegram_second == []


def test_one_off_reaches_second_destination_after_first_destination_made_it_inactive(
    store,
):
    # The defect M6 existed to fix: before per-destination delivery the first
    # destination consumed the reminder globally, so a second destination that
    # had not seen it never would. Here the terminal consumes the one-off, the
    # row goes inactive, and the telegram destination must still receive it.
    now = time.time()
    store.add_reminder("pay the electric bill", now - 10)

    first = store.check_due_reminders(now=now, destination="terminal")
    assert len(first) == 1
    assert first[0].text == "pay the electric bill"
    # The one-off row is now inactive for the terminal destination.
    assert first[0].active is False

    second = store.check_due_reminders(now=now, destination="telegram")
    assert len(second) == 1
    assert second[0].text == "pay the electric bill"

    # Telegram has now consumed it too; a third call to either is silent.
    assert store.check_due_reminders(now=now, destination="telegram") == []
    assert store.check_due_reminders(now=now, destination="terminal") == []


def test_monthly_reminder_advances_one_period_no_matter_how_many_destinations_read_it(
    store,
):
    # Measured: about thirty days after two destinations both read a monthly
    # reminder, not sixty. Each destination reads the same single advance.
    now = time.time()
    added = store.add_reminder("monthly instalment", now - 10, repeat_months=1)
    expected_next = advance_due_date(added.due_at, None, 1, added.anchor_day)

    terminal = store.check_due_reminders(now=now, destination="terminal")
    telegram = store.check_due_reminders(now=now, destination="telegram")

    assert len(terminal) == 1
    assert len(telegram) == 1

    # Both destinations see the same single advance to the next month.
    assert terminal[0].due_at == expected_next
    assert telegram[0].due_at == expected_next
    assert telegram[0].due_at == terminal[0].due_at

    # The advance is one Jalali month (~30 days), not two (~60). A regression
    # that advanced once per reading destination would break this bound.
    one_month = expected_next - added.due_at
    assert 25 * 86_400 < one_month < 35 * 86_400


def test_default_destination_fires_once_then_returns_nothing_for_a_lone_terminal(
    store,
):
    # With no destination argument the check fires exactly once and then is
    # silent, exactly as it behaved before per-destination delivery existed.
    now = time.time()
    store.add_reminder("lone terminal reminder", now - 10)

    first = store.check_due_reminders(now=now)
    assert len(first) == 1
    assert first[0].text == "lone terminal reminder"

    second = store.check_due_reminders(now=now)
    assert second == []


def test_brand_new_destination_receives_every_overdue_reminder_at_once(store):
    # A destination the store has never seen does not inherit the historical
    # pile-up, but it DOES receive every currently-overdue reminder in one
    # batch. The terminal consumes both first; a brand-new destination
    # checking at the same instant then receives both as well. This is the
    # behaviour the code has today, pinned as-is — see the pull request for
    # whether it is the right behaviour.
    now = time.time()
    store.add_reminder("overdue one", now - 10)
    store.add_reminder("overdue two", now - 10)

    terminal = store.check_due_reminders(now=now, destination="terminal")
    assert len(terminal) == 2

    brand_new = store.check_due_reminders(now=now, destination="never-seen-before")
    assert len(brand_new) == 2
    assert {r.text for r in brand_new} == {"overdue one", "overdue two"}


def test_old_database_gains_the_two_delivery_tables_and_keeps_its_data(tmp_path):
    # Measured: a store built on the previous release with one memory and one
    # reminder, reopened, still reports one and one, and the two new tables
    # exist. The previous release left no delivery tables; the migration adds
    # them in place without dropping data.
    db_path = str(tmp_path / "previous-release.db")
    now = time.time()

    conn = sqlite3.connect(db_path)
    conn.executescript(_PREVIOUS_RELEASE_SCHEMA)
    conn.execute(
        "INSERT INTO memories (kind, content, norm, created_at, last_used_at) "
        "VALUES ('semantic', ?, ?, ?, ?)",
        ("one memory", "one memory", now, now),
    )
    conn.execute(
        "INSERT INTO reminders (text, due_at, next_due, created_at) "
        "VALUES ('one reminder', ?, ?, ?)",
        (now - 10, now - 10, now),
    )
    conn.commit()
    tables_before = _table_names(conn)
    conn.close()

    assert "reminder_deliveries" not in tables_before
    assert "reminder_destinations" not in tables_before

    with MemoryStore(db_path) as reopened:
        tables_after = _table_names(reopened.conn)
        memory_count = reopened.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        reminder_count = reopened.conn.execute(
            "SELECT COUNT(*) FROM reminders"
        ).fetchone()[0]

    assert "reminder_deliveries" in tables_after
    assert "reminder_destinations" in tables_after
    assert memory_count == 1
    assert reminder_count == 1
