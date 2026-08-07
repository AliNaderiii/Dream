"""Pin the reminder scheduling engine and its hazards.

The owner relies on monthly and weekly reminders for insurance and
instalments. The engine must survive pile-up (four months overdue gives
one notice), clock jumps backwards, and concurrent due checks. Every
query filters by user, one-offs become inactive, repeats advance in
Jalali months with clamping, and the startup notice respects --quiet
without muting command replies. These tests reproduce the measured
behaviours that justified the design.
"""

from __future__ import annotations

import io
import sqlite3
import sys
import threading
import time

import pytest

import cli
from dream.jalali import gregorian_to_jalali
from dream.memory import MemoryStore
from dream.reminders import advance_due_date, format_jalali, parse_date_to_timestamp


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "rem.db"))
    yield s
    s.close()


def _ts(jy, jm, jd):
    return parse_date_to_timestamp(f"{jy:04d}-{jm:02d}-{jd:02d}")


def test_due_in_past_reported_future_not(store):
    now = time.time()
    past = now - 86400
    future = now + 86400
    store.add_reminder("past", past)
    store.add_reminder("future", future)
    due = store.check_due_reminders(now=now)
    assert len(due) == 1
    assert due[0].text == "past"


def test_one_off_fires_once_then_inactive(store):
    now = time.time()
    past = now - 100
    store.add_reminder("once", past)
    first = store.check_due_reminders(now=now)
    assert len(first) == 1
    assert first[0].active is False
    second = store.check_due_reminders(now=now)
    assert len(second) == 0
    all_rems = store.list_reminders(include_inactive=True)
    assert len([r for r in all_rems if not r.active]) == 1


def test_repeating_fires_and_moves_into_future(store):
    now = time.time()
    past = now - 100
    store.add_reminder("weekly", past, repeat_days=7)
    due = store.check_due_reminders(now=now)
    assert len(due) == 1
    assert due[0].due_at > now
    assert len(store.check_due_reminders(now=now)) == 0


def test_pile_up_several_periods_overdue_one_notice(store):
    now = time.time()
    gy, gm, gd = time.gmtime(now)[:3]
    jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
    total = jy * 12 + (jm - 1) - 4
    njy = total // 12
    njm = total % 12 + 1
    from dream.jalali import is_jalali_leap

    def dim(y, m):
        if 1 <= m <= 6:
            return 31
        if 7 <= m <= 11:
            return 30
        return 30 if is_jalali_leap(y) else 29

    njd = min(jd, dim(njy, njm))
    past = parse_date_to_timestamp(f"{njy:04d}-{njm:02d}-{njd:02d}")
    store.add_reminder("monthly pile", past, repeat_months=1)
    first = store.check_due_reminders(now=now)
    assert len(first) == 1
    assert first[0].due_at > now
    assert len(store.check_due_reminders(now=now)) == 0


def test_monthly_from_31st_lands_on_last_day(store):
    ts = _ts(1405, 5, 31)
    nxt = advance_due_date(ts, None, 1)
    assert format_jalali(nxt) == "1405-06-31"
    nxt2 = advance_due_date(nxt, None, 1)
    assert format_jalali(nxt2) == "1405-07-30"


def test_monthly_across_esfand_leap_and_common(store):
    ts_leap = _ts(1399, 11, 30)
    assert format_jalali(advance_due_date(ts_leap, None, 1)) == "1399-12-30"
    ts_common = _ts(1400, 11, 30)
    assert format_jalali(advance_due_date(ts_common, None, 1)) == "1400-12-29"
    assert format_jalali(advance_due_date(_ts(1399, 12, 30), None, 1)) == "1400-01-30"


def test_clock_backwards_neither_refires_nor_lost(store):
    now = time.time()
    past = now - 100
    store.add_reminder("clock test", past, repeat_days=7)
    first = store.check_due_reminders(now=now)
    assert len(first) == 1
    earlier = now - 500
    second = store.check_due_reminders(now=earlier)
    assert len(second) == 0
    later = now + 8 * 86400
    third = store.check_due_reminders(now=later)
    assert len(third) == 1


def test_two_threads_check_once_each_fires_once(tmp_path):
    s = MemoryStore(str(tmp_path / "thr.db"))
    now = time.time()
    for i in range(5):
        s.add_reminder(f"thr {i}", now - 10)
    results: list[int] = []

    def worker():
        results.append(len(s.check_due_reminders(now=now)))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == 5
    assert sorted(results) == [0, 0, 0, 0, 5]
    assert len(s.check_due_reminders(now=now)) == 0
    s.close()


def test_reminders_isolated_by_user(tmp_path):
    db = str(tmp_path / "users.db")
    with MemoryStore(db, user="alice") as a:
        a.add_reminder("alice only", time.time() - 100)
    with MemoryStore(db, user="bob") as b:
        assert len(b.list_reminders()) == 0
        assert len(b.check_due_reminders()) == 0
    with MemoryStore(db, user="alice") as a2:
        assert len(a2.check_due_reminders()) == 1


def test_add_command_accepts_jalali_and_gregorian_same_timestamp(tmp_path):
    s = MemoryStore(str(tmp_path / "same.db"))
    ts_j = parse_date_to_timestamp("1405-05-16")
    ts_g = parse_date_to_timestamp("2026-08-07")
    assert ts_j == ts_g
    r1 = s.add_reminder("via jalali", ts_j)
    s2 = MemoryStore(str(tmp_path / "same2.db"))
    r2 = s2.add_reminder("via gregorian", ts_g)
    assert r1.due_at == r2.due_at
    from dream.agent import Dream, EchoBackend

    store = MemoryStore(str(tmp_path / "cli.db"))
    dream = Dream(store, EchoBackend())
    out: list[str] = []
    cli.dispatch_command("/remind 1405-05-16 jalali text", dream, out.append)
    # second line uses different year but same timestamp
    cli.dispatch_command(
        "/remind 2026-08-07 gregorian text",
        Dream(store, EchoBackend()),
        out.append,
    )
    rems = store.list_reminders()
    jal = [r for r in rems if r.text == "jalali text"]
    greg = [r for r in rems if r.text == "gregorian text"]
    assert jal and greg
    assert jal[0].due_at == greg[0].due_at


def test_add_command_rejects_bad_input():
    from dream.agent import Dream, EchoBackend

    cases = [
        ("/remind not-a-date text", "Unparseable"),
        ("/remind 1400-12-30 text", "Invalid date"),
        ("/remind 1405-13-01 text", "Invalid date"),
        ("/remind 1405-07-31 text", "Invalid date"),
        ("/remind 1405-05-16", "Missing text"),
        ("/remind 1405-05-16 every 0 days text", "non-zero"),
    ]
    for cmd, substr in cases:
        store = MemoryStore(":memory:")
        dream = Dream(store, EchoBackend())
        out: list[str] = []
        cli.dispatch_command(cmd, dream, out.append)
        assert out, f"no output for {cmd}"
        assert substr.lower() in out[0].lower(), f"{cmd} gave {out[0]!r}"
        assert len(store.list_reminders()) == 0


def test_list_shows_due_date_in_jalali(store):
    ts = _ts(1405, 5, 16)
    store.add_reminder("\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0633\u062a", ts)
    from dream.agent import Dream, EchoBackend

    dream = Dream(store, EchoBackend())
    out: list[str] = []
    cli.dispatch_command("/reminders", dream, out.append)
    assert out
    assert "1405-05-16" in out[0]


def _feeding_input(lines):
    it = iter(lines)

    def read(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return read


def test_startup_notice_respects_quiet_and_replies_visible(tmp_path, monkeypatch):
    db = str(tmp_path / "startup.db")
    with MemoryStore(db) as s:
        s.add_reminder("notice text", time.time() - 100)
    # without quiet, notice on stderr
    monkeypatch.setattr("builtins.input", _feeding_input(["/reminders", "/exit"]))
    old_out, old_err = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = buf_out, buf_err
    try:
        cli.main(["--db", db])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    # need to re-add because one-off was consumed
    with MemoryStore(db) as s:
        if not s.list_reminders():
            s.add_reminder("notice text", time.time() - 100)
    monkeypatch.setattr("builtins.input", _feeding_input(["/reminders", "/exit"]))
    buf_out, buf_err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = buf_out, buf_err
    try:
        cli.main(["--db", db])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        monkeypatch.undo()
    assert "[reminder]" in buf_err.getvalue()
    # with quiet, no bracketed line but reply still visible
    with MemoryStore(db) as s:
        if not s.list_reminders():
            s.add_reminder("quiet text", time.time() - 100)
    monkeypatch.setattr("builtins.input", _feeding_input(["/reminders", "/exit"]))
    buf_out, buf_err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = buf_out, buf_err
    try:
        cli.main(["--db", db, "--quiet"])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        monkeypatch.undo()
    assert "[reminder]" not in buf_err.getvalue()
    assert buf_out.getvalue()


def test_no_reminders_prints_nothing_at_startup(tmp_path, monkeypatch):
    db = str(tmp_path / "empty.db")
    MemoryStore(db).close()
    monkeypatch.setattr("builtins.input", _feeding_input(["/exit"]))
    old_out, old_err = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = buf_out, buf_err
    try:
        cli.main(["--db", db])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        monkeypatch.undo()
    assert "[reminder]" not in buf_err.getvalue()
    assert buf_err.getvalue().strip() == ""


def test_old_db_migration_is_noop(tmp_path):
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    # long line split to keep ruff happy
    conn.execute(
        "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id TEXT NOT NULL DEFAULT 'local', kind TEXT NOT NULL, "
        "content TEXT NOT NULL, norm TEXT NOT NULL, tags TEXT NOT NULL, "
        "importance REAL, created_at REAL, last_used_at REAL, "
        "use_count INTEGER, source TEXT, archived INTEGER, "
        "superseded_by INTEGER, pinned INTEGER)"
    )
    conn.execute(
        "CREATE TABLE journal (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id TEXT NOT NULL DEFAULT 'local', ts REAL, role TEXT, "
        "content TEXT, session_id TEXT)"
    )
    conn.commit()
    conn.close()
    with MemoryStore(db) as s:
        assert s.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='reminders'"
        ).fetchone()
    with MemoryStore(db) as s2:
        assert s2.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='reminders'"
        ).fetchone()


def test_quiet_does_not_mute_command_replies(tmp_path, monkeypatch):
    db = str(tmp_path / "quiet2.db")
    with MemoryStore(db) as s:
        s.remember("quiet visible fact")
    monkeypatch.setattr(
        "builtins.input",
        _feeding_input(["/mems", "/help", "/reminders", "/exit"]),
    )
    old_out, old_err = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = buf_out, buf_err
    try:
        cli.main(["--db", db, "--quiet"])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        monkeypatch.undo()
    out = buf_out.getvalue()
    err = buf_err.getvalue()
    assert "quiet visible fact" in out
    assert "/remind" in out
    assert "[reminder]" not in err
