"""Reminder scheduling: storage helpers and due checks.

Persian dates are stored as Unix timestamps; conversion uses
``dream.jalali`` only at the edges. Repeats are either a fixed number
of days or a fixed number of months. Adding a month is Jalali-aware and
clamps to the last day of the target month, including Esfand in both
leap and common years.

New Persian strings are written as backslash-u escapes.
"""

from __future__ import annotations

import calendar
import datetime
import re
import time
from dataclasses import dataclass

from dream.jalali import (
    gregorian_to_jalali,
    is_jalali_leap,
    jalali_to_gregorian,
)

__all__ = [
    "Reminder",
    "add_reminder",
    "advance_due_date",
    "check_due_reminders",
    "format_jalali",
    "list_reminders",
    "parse_date_to_timestamp",
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Reminder:
    """A scheduled reminder."""

    id: int
    user_id: str
    text: str
    due_at: float
    next_due: float
    repeat_days: int | None
    repeat_months: int | None
    last_fired_at: float | None
    created_at: float
    active: bool
    anchor_day: int | None = None


def _row_to_reminder(row) -> Reminder:
    return Reminder(
        id=int(row["id"]),
        user_id=str(row["user_id"]),
        text=str(row["text"]),
        due_at=float(row["due_at"]),
        next_due=float(row["next_due"]) if row["next_due"] is not None else float(row["due_at"]),
        repeat_days=int(row["repeat_days"]) if row["repeat_days"] is not None else None,
        repeat_months=int(row["repeat_months"]) if row["repeat_months"] is not None else None,
        last_fired_at=float(row["last_fired_at"]) if row["last_fired_at"] is not None else None,
        created_at=float(row["created_at"]),
        active=bool(row["active"]),
        anchor_day=int(row["anchor_day"]) if "anchor_day" in row.keys() and row["anchor_day"] is not None else None,  # noqa: E501
    )


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _gregorian_to_timestamp(gy: int, gm: int, gd: int) -> float:
    """Return UTC midnight timestamp for a Gregorian date."""
    return calendar.timegm((gy, gm, gd, 0, 0, 0, 0, 0, 0))


def _jalali_to_timestamp(jy: int, jm: int, jd: int) -> float:
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    return _gregorian_to_timestamp(gy, gm, gd)


def _timestamp_to_gregorian(ts: float) -> tuple[int, int, int]:
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.year, dt.month, dt.day


def _timestamp_to_jalali(ts: float) -> tuple[int, int, int]:
    gy, gm, gd = _timestamp_to_gregorian(ts)
    return gregorian_to_jalali(gy, gm, gd)


def format_jalali(ts: float) -> str:
    """Format a timestamp as Jalali YYYY-MM-DD."""
    jy, jm, jd = _timestamp_to_jalali(ts)
    return f"{jy:04d}-{jm:02d}-{jd:02d}"


def _days_in_jalali_month(year: int, month: int) -> int:
    if 1 <= month <= 6:
        return 31
    if 7 <= month <= 11:
        return 30
    if month == 12:
        return 30 if is_jalali_leap(year) else 29
    return 0


def advance_due_date(
    due_at: float,
    repeat_days: int | None,
    repeat_months: int | None,
    anchor_day: int | None = None,
) -> float:
    """Advance a due timestamp by one repeat interval, Jalali-aware.

    Adding a month is not adding thirty days: the thirty-first of a month
    plus one month lands on the last day of the following month when that
    month is shorter, not spilling into the month after. End of Esfand in
    both leap and common years is handled via clamping.

    When *anchor_day* is given, monthly advances are computed from that
    anchor, not from the previous clamped day, so a series anchored on 31
    returns to 31 after a short month. Day repeats never use the anchor.
    """
    if repeat_days is not None:
        return due_at + repeat_days * 86400
    if repeat_months is not None:
        jy, jm, _jd = _timestamp_to_jalali(due_at)
        jd = anchor_day if anchor_day is not None else _jd
        total = jy * 12 + (jm - 1) + repeat_months
        new_jy = total // 12
        new_jm = total % 12 + 1
        max_day = _days_in_jalali_month(new_jy, new_jm)
        new_jd = jd if jd <= max_day else max_day
        return _jalali_to_timestamp(new_jy, new_jm, new_jd)
    return due_at


def parse_date_to_timestamp(text: str) -> float:
    """Parse YYYY-MM-DD, accepting Jalali when year < 1700.

    A year below 1700 is Jalali. Say so in a comment.
    Accepted separators are hyphen, slash, or dot.
    """
    # year below 1700 is Jalali
    m = re.match(r"^\s*(\d{4})\s*[-/.\s]\s*(\d{1,2})\s*[-/.\s]\s*(\d{1,2})\s*$", text.strip())
    if not m:
        raise ValueError(f"unparseable date: {text!r}")
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 1700:
        # Jalali input
        return _jalali_to_timestamp(y, mo, d)
    return _gregorian_to_timestamp(y, mo, d)


# ---------------------------------------------------------------------------
# Store operations
# ---------------------------------------------------------------------------


def add_reminder(
    store,
    text: str,
    due_at: float,
    repeat_days: int | None = None,
    repeat_months: int | None = None,
) -> Reminder:
    """Add a reminder for the owning user."""
    if not text or not text.strip():
        raise ValueError("text must not be empty")
    if repeat_days is not None and repeat_days == 0:
        raise ValueError("repeat must be non-zero")
    if repeat_months is not None and repeat_months == 0:
        raise ValueError("repeat must be non-zero")
    if repeat_days is not None and repeat_months is not None:
        raise ValueError("repeat must be either days or months, not both")
    text = text.strip()
    now = time.time()
    # anchor_day stores the owner's original day-of-month for monthly repeats
    _, _, anchor_day = _timestamp_to_jalali(float(due_at))
    with store._lock:
        cur = store.conn.execute(
            """INSERT INTO reminders
               (user_id, text, due_at, next_due, repeat_days, repeat_months,
                last_fired_at, created_at, active, anchor_day)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 1, ?)""",
            (
                store.user_id,
                text,
                float(due_at),
                float(due_at),
                repeat_days,
                repeat_months,
                float(now),
                anchor_day,
            ),
        )
        store.conn.commit()
        rid = int(cur.lastrowid)
        row = store.conn.execute(
            "SELECT * FROM reminders WHERE user_id = ? AND id = ?",
            (store.user_id, rid),
        ).fetchone()
        return _row_to_reminder(row)


def list_reminders(store, include_inactive: bool = False) -> list[Reminder]:
    """List reminders for the owning user, active by default."""
    with store._lock:
        sql = "SELECT * FROM reminders WHERE user_id = ?"
        params: list = [store.user_id]
        if not include_inactive:
            sql += " AND active = 1"
        sql += " ORDER BY due_at ASC"
        rows = store.conn.execute(sql, params).fetchall()
        return [_row_to_reminder(r) for r in rows]


def check_due_reminders(
    store,
    now: float | None = None,
) -> list[Reminder]:
    """Find due reminders, notify once, and advance to the future.

    Handles three hazards:
    - pile-up: notify once, then advance repeatedly until future
    - clock backwards: never move a due date backwards, record last_fired_at
    - concurrent copies: one transaction under the store lock

    Returns the list of reminders that fired in this pass.
    """
    if now is None:
        now = time.time()
    now = float(now)
    fired: list[Reminder] = []
    with store._lock:
        store.conn.execute("BEGIN")
        try:
            rows = store.conn.execute(
                """SELECT * FROM reminders
                   WHERE user_id = ? AND active = 1 AND due_at <= ?""",
                (store.user_id, now),
            ).fetchall()
            for row in rows:
                rid = int(row["id"])
                due_at = float(row["due_at"])
                repeat_days = row["repeat_days"]
                repeat_months = row["repeat_months"]
                # anchor_day keeps the owner's original day, avoiding ratchet
                try:
                    anchor_day = (
                        int(row["anchor_day"])
                        if "anchor_day" in row.keys() and row["anchor_day"] is not None
                        else None
                    )
                except Exception:
                    anchor_day = None
                if anchor_day is None and repeat_months is not None:
                    # fallback for rows created before the column existed
                    _, _, anchor_day = _timestamp_to_jalali(due_at)
                # re-read to handle concurrent? already in transaction
                if repeat_days is None and repeat_months is None:
                    # one-off becomes inactive
                    store.conn.execute(
                        """UPDATE reminders
                           SET active = 0, last_fired_at = ?
                           WHERE user_id = ? AND id = ?""",
                        (now, store.user_id, rid),
                    )
                    fresh = store.conn.execute(
                        "SELECT * FROM reminders WHERE user_id = ? AND id = ?",
                        (store.user_id, rid),
                    ).fetchone()
                    fired.append(
                        _row_to_reminder(fresh) if fresh is not None else _row_to_reminder(row)
                    )
                else:
                    # pile-up: advance repeatedly until future, one notice
                    new_due = due_at
                    # avoid infinite loop if repeat is somehow zero
                    if (repeat_days is not None and repeat_days == 0) or (
                        repeat_months is not None and repeat_months == 0
                    ):
                        continue
                    # advance from the stored due date, never backwards
                    original_due = float(row["due_at"])
                    while new_due <= now:
                        next_due = advance_due_date(
                            new_due, repeat_days, repeat_months, anchor_day
                        )
                        if next_due <= new_due:
                            break
                        new_due = next_due
                        if new_due > now:
                            break
                    # ensure we never move backwards relative to original
                    if new_due < original_due:
                        new_due = original_due
                    store.conn.execute(
                        """UPDATE reminders
                           SET due_at = ?, next_due = ?, last_fired_at = ?
                           WHERE user_id = ? AND id = ?""",
                        (float(new_due), float(new_due), float(now), store.user_id, rid),
                    )
                    # fetch fresh row for accuracy
                    fresh = store.conn.execute(
                        "SELECT * FROM reminders WHERE user_id = ? AND id = ?",
                        (store.user_id, rid),
                    ).fetchone()
                    if fresh is not None:
                        fired.append(_row_to_reminder(fresh))
                    else:
                        fired.append(_row_to_reminder(row))
            store.conn.commit()
        except Exception:
            store.conn.rollback()
            raise
    return fired
