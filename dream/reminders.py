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
from dream.memory import _stem_fa, _tokenize, normalize_fa

__all__ = [
    "DUE_SOON_WINDOW_SECONDS",
    "MAX_REMINDER_LINES",
    "Reminder",
    "add_reminder",
    "advance_due_date",
    "check_due_reminders",
    "delete_reminder",
    "format_jalali",
    "list_reminders",
    "parse_date_to_timestamp",
    "parse_persian_date",
    "prompt_reminders",
]

# A reminder falls due "soon" when its due date is within this horizon. Seven
# days covers next week's obligations without flooding the prompt with the
# owner's entire far-future schedule.
DUE_SOON_WINDOW_SECONDS = 7 * 24 * 3600.0

# At most this many reminders reach the model prompt in one turn. The prompt
# is for answering, not for dumping the whole calendar.
MAX_REMINDER_LINES = 5

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


def prompt_reminders(
    reminders: list[Reminder],
    query: str,
    now: float | None = None,
    limit: int = MAX_REMINDER_LINES,
) -> list[Reminder]:
    """Choose the reminders that reach the model prompt for one turn.

    A reminder qualifies when it is relevant to the current query (shares at
    least one normalised, stemmed token with it) or falls due within the soon
    window, so something due regardless of the query is still surfaced. The
    owner's far-future schedule stays out unless the turn concerns it.

    Candidates are ranked by relevance plus an urgency bonus: overdue scores
    1.0, due-soon 0.5, future 0. Ties keep ``list_reminders``'s due-date
    order because the sort is stable. The ranked list is capped at *limit*.
    """
    if limit <= 0 or not reminders:
        return []
    if now is None:
        now = time.time()
    now = float(now)
    horizon = now + DUE_SOON_WINDOW_SECONDS
    query_stems = {_stem_fa(token) for token in _tokenize(query)}
    scored: list[tuple[float, Reminder]] = []
    for reminder in reminders:
        stems = {_stem_fa(token) for token in _tokenize(reminder.text)}
        relevance = len(stems & query_stems) / len(stems) if stems else 0.0
        if reminder.due_at <= now:
            urgency = 1.0
        elif reminder.due_at <= horizon:
            urgency = 0.5
        else:
            urgency = 0.0
        if relevance > 0.0 or urgency > 0.0:
            scored.append((relevance + urgency, reminder))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [reminder for _, reminder in scored[:limit]]


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


def delete_reminder(store, reminder_id: int) -> bool:
    """Delete a reminder by id, filtered by user. Returns True if deleted."""
    with store._lock:
        cur = store.conn.execute(
            "DELETE FROM reminders WHERE user_id = ? AND id = ?",
            (store.user_id, reminder_id),
        )
        store.conn.commit()
        return cur.rowcount > 0


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

# ---------------------------------------------------------------------------
# Natural Persian dates (M3)
#
# Parses the phrases real people type — «فردا», «پانزدهم مهر», «اول هر ماه» —
# into the same midnight timestamps the scheduler already uses. The Jalali
# module stays the single source of calendar truth; this block only turns
# words into dates. Ambiguous input raises ValueError with a worked example,
# never a guess. Every Persian string is a backslash-u escape; the inline
# glosses give the plain spellings.
# ---------------------------------------------------------------------------

# Jalali month names in order. Glosses: فروردین، اردیبهشت، خرداد، تیر، مرداد،
# شهریور، مهر، آبان، آذر، دی، بهمن، اسفند.
_MONTHS: tuple[tuple[int, str], ...] = (
    (1, "\u0641\u0631\u0648\u0631\u062f\u06cc\u0646"),  # فروردین
    (2, "\u0627\u0631\u062f\u06cc\u0628\u0647\u0634\u062a"),  # اردیبهشت
    (3, "\u062e\u0631\u062f\u0627\u062f"),  # خرداد
    (4, "\u062a\u06cc\u0631"),  # تیر
    (5, "\u0645\u0631\u062f\u0627\u062f"),  # مرداد
    (6, "\u0634\u0647\u0631\u06cc\u0648\u0631"),  # شهریور
    (7, "\u0645\u0647\u0631"),  # مهر
    (8, "\u0627\u0628\u0627\u0646"),  # آبان
    (9, "\u0627\u0630\u0631"),  # آذر
    (10, "\u062f\u06cc"),  # دی
    (11, "\u0628\u0647\u0645\u0646"),  # بهمن
    (12, "\u0627\u0633\u0641\u0646\u062f"),  # اسفند
)

_MONTH_LOOKUP: dict[str, int] = {name: number for number, name in _MONTHS}


def _month_name(month: int) -> str:
    """The Jalali month name for month 1..12 (for error examples)."""
    return _MONTHS[month - 1][1]


# Day words: (canonical spaced form, day number). Both ordinals («پانزدهم»)
# and colloquial cardinals («پانزده») mean the same day; the compact and
# ZWNJ spellings collapse onto the spaced form via normalisation plus the
# space-insensitive matchers below. Glosses list the plain spellings.
_DAY_WORDS: tuple[tuple[str, int], ...] = (
    ("\u0627\u0648\u0644", 1),  # 1: اول
    ("\u06cc\u06a9\u0645", 1),  # 1: یکم
    ("\u062f\u0648\u0645", 2),  # 2: دوم
    ("\u0633\u0648\u0645", 3),  # 3: سوم
    ("\u0686\u0647\u0627\u0631\u0645", 4),  # 4: چهارم
    ("\u067e\u0646\u062c\u0645", 5),  # 5: پنجم
    ("\u0634\u0634\u0645", 6),  # 6: ششم
    ("\u0647\u0641\u062a\u0645", 7),  # 7: هفتم
    ("\u0647\u0634\u062a\u0645", 8),  # 8: هشتم
    ("\u0646\u0647\u0645", 9),  # 9: نهم
    ("\u062f\u0647\u0645", 10),  # 10: دهم
    ("\u06cc\u0627\u0632\u062f\u0647\u0645", 11),  # 11: یازدهم
    ("\u062f\u0648\u0627\u0632\u062f\u0647\u0645", 12),  # 12: دوازدهم
    ("\u0633\u06cc\u0632\u062f\u0647\u0645", 13),  # 13: سیزدهم
    ("\u0686\u0647\u0627\u0631\u062f\u0647\u0645", 14),  # 14: چهاردهم
    ("\u067e\u0627\u0646\u0632\u062f\u0647\u0645", 15),  # 15: پانزدهم
    ("\u0634\u0627\u0646\u0632\u062f\u0647\u0645", 16),  # 16: شانزدهم
    ("\u0647\u0641\u062f\u0647\u0645", 17),  # 17: هفدهم
    ("\u0647\u062c\u062f\u0647\u0645", 18),  # 18: هجدهم
    ("\u0646\u0648\u0632\u062f\u0647\u0645", 19),  # 19: نوزدهم
    ("\u0628\u06cc\u0633\u062a\u0645", 20),  # 20: بیستم
    ("\u0628\u06cc\u0633\u062a \u0648 \u06cc\u06a9\u0645", 21),  # 21: بیست و یکم
    ("\u0628\u06cc\u0633\u062a \u0648 \u062f\u0648\u0645", 22),  # 22: بیست و دوم
    ("\u0628\u06cc\u0633\u062a \u0648 \u0633\u0648\u0645", 23),  # 23: بیست و سوم
    ("\u0628\u06cc\u0633\u062a \u0648 \u0686\u0647\u0627\u0631\u0645", 24),  # 24: بیست و چهارم
    ("\u0628\u06cc\u0633\u062a \u0648 \u067e\u0646\u062c\u0645", 25),  # 25: بیست و پنجم
    ("\u0628\u06cc\u0633\u062a \u0648 \u0634\u0634\u0645", 26),  # 26: بیست و ششم
    ("\u0628\u06cc\u0633\u062a \u0648 \u0647\u0641\u062a\u0645", 27),  # 27: بیست و هفتم
    ("\u0628\u06cc\u0633\u062a \u0648 \u0647\u0634\u062a\u0645", 28),  # 28: بیست و هشتم
    ("\u0628\u06cc\u0633\u062a \u0648 \u0646\u0647\u0645", 29),  # 29: بیست و نهم
    ("\u0633\u06cc \u0627\u0645", 30),  # 30: سی ام
    ("\u0633\u06cc \u0648 \u06cc\u06a9\u0645", 31),  # 31: سی و یکم
    ("\u06cc\u06a9", 1),  # 1: یک
    ("\u062f\u0648", 2),  # 2: دو
    ("\u0633\u0647", 3),  # 3: سه
    ("\u0686\u0647\u0627\u0631", 4),  # 4: چهار
    ("\u067e\u0646\u062c", 5),  # 5: پنج
    ("\u0634\u0634", 6),  # 6: شش
    ("\u0647\u0641\u062a", 7),  # 7: هفت
    ("\u0647\u0634\u062a", 8),  # 8: هشت
    ("\u0646\u0647", 9),  # 9: نه
    ("\u062f\u0647", 10),  # 10: ده
    ("\u06cc\u0627\u0632\u062f\u0647", 11),  # 11: یازده
    ("\u062f\u0648\u0627\u0632\u062f\u0647", 12),  # 12: دوازده
    ("\u0633\u06cc\u0632\u062f\u0647", 13),  # 13: سیزده
    ("\u0686\u0647\u0627\u0631\u062f\u0647", 14),  # 14: چهارده
    ("\u067e\u0627\u0646\u0632\u062f\u0647", 15),  # 15: پانزده
    ("\u0634\u0627\u0646\u0632\u062f\u0647", 16),  # 16: شانزده
    ("\u0647\u0641\u062f\u0647", 17),  # 17: هفده
    ("\u0647\u062c\u062f\u0647", 18),  # 18: هجده
    ("\u0646\u0648\u0632\u062f\u0647", 19),  # 19: نوزده
    ("\u0628\u06cc\u0633\u062a", 20),  # 20: بیست
    ("\u0628\u06cc\u0633\u062a \u0648 \u06cc\u06a9", 21),  # 21: بیست و یک
    ("\u0628\u06cc\u0633\u062a \u0648 \u062f\u0648", 22),  # 22: بیست و دو
    ("\u0628\u06cc\u0633\u062a \u0648 \u0633\u0647", 23),  # 23: بیست و سه
    ("\u0628\u06cc\u0633\u062a \u0648 \u0686\u0647\u0627\u0631", 24),  # 24: بیست و چهار
    ("\u0628\u06cc\u0633\u062a \u0648 \u067e\u0646\u062c", 25),  # 25: بیست و پنج
    ("\u0628\u06cc\u0633\u062a \u0648 \u0634\u0634", 26),  # 26: بیست و شش
    ("\u0628\u06cc\u0633\u062a \u0648 \u0647\u0641\u062a", 27),  # 27: بیست و هفت
    ("\u0628\u06cc\u0633\u062a \u0648 \u0647\u0634\u062a", 28),  # 28: بیست و هشت
    ("\u0628\u06cc\u0633\u062a \u0648 \u0646\u0647", 29),  # 29: بیست و نه
    ("\u0633\u06cc", 30),  # 30: سی
    ("\u0633\u06cc \u0648 \u06cc\u06a9", 31),  # 31: سی و یک
)

_DAY_COMPACT: dict[str, int] = {word.replace(" ", ""): day for word, day in _DAY_WORDS}

# Weekday names: (canonical spaced form, Gregorian weekday Monday=0).
# «یکشنبه» and «سه‌شنبه» are written with an optional space so joined, ZWNJ,
# and spaced spellings all match after normalisation. Glosses list the plain
# spellings: شنبه، یکشنبه، دوشنبه، سه‌شنبه، چهارشنبه، پنج‌شنبه، جمعه.
_WEEKDAY_LOOKUP: dict[str, int] = {
    "\u0634\u0646\u0628\u0647": 5,  # شنبه
    "\u06cc\u06a9 \u0634\u0646\u0628\u0647": 6,  # یکشنبه
    "\u062f\u0648\u0634\u0646\u0628\u0647": 0,  # دوشنبه
    "\u0633\u0647 \u0634\u0646\u0628\u0647": 1,  # سه‌شنبه
    "\u0686\u0647\u0627\u0631 \u0634\u0646\u0628\u0647": 2,  # چهارشنبه
    "\u067e\u0646\u062c \u0634\u0646\u0628\u0647": 3,  # پنج‌شنبه
    "\u062c\u0645\u0639\u0647": 4,  # جمعه
}

_WEEKDAY_COMPACT: dict[str, int] = {
    word.replace(" ", ""): weekday for word, weekday in _WEEKDAY_LOOKUP.items()
}

# Pattern building: day words are matched space-insensitively (a space becomes
# \s*), so «بیست‌ویکم», «بیست‌و‌یکم» and «بیست و یکم» are the same day.
_DAY_ALTERNATION = "|".join(
    sorted(
        (word.replace(" ", r"\s*") for word, _ in _DAY_WORDS),
        key=len,
        reverse=True,
    )
)
_DIGIT_DAY = r"\d{1,2}(?:\s*\u0627\u0645)?"  # 15 / ۱۵ام / ۱۵ ام
_DAY_ONLY_RE = re.compile(r"^(?:" + _DAY_ALTERNATION + "|" + _DIGIT_DAY + r")$")
_MONTH_DAY_RE = re.compile(
    r"^(?P<day>" + _DAY_ALTERNATION + "|" + _DIGIT_DAY + r")\s+(?P<month>"
    + "|".join(sorted((name for _, name in _MONTHS), key=len, reverse=True))
    + r")(?:\s+(?P<year>\d{4}))?$"
)
# «اول هر ماه», «پانزدهم هر ماه» — a day of every month, next occurrence.
_EVERY_MONTH_RE = re.compile(
    r"^(?P<day>" + _DAY_ALTERNATION + "|" + _DIGIT_DAY + r")\s+"
    + "\u0647\u0631 \u0645\u0627\u0647$"
)
_WEEKDAY_RE = re.compile(
    r"^(?P<day>"
    + "|".join(
        sorted(
            (word.replace(" ", r"\s*") for word in _WEEKDAY_LOOKUP),
            key=len,
            reverse=True,
        )
    )
    + r")(?:\s+(?P<week>"
    + "\u0647\u0641\u062a\u0647"
    + r"\s*(?:\u0628\u0639\u062f|\u0627\u06cc\u0646\u062f\u0647)))?$"
)
_RELATIVE_RE = re.compile(
    r"^(?P<num>" + _DAY_ALTERNATION + r"|\d{1,4})\s+(?P<unit>"
    + "\u0631\u0648\u0632|\u0647\u0641\u062a\u0647|\u0645\u0627\u0647|\u0633\u0627\u0644"
    + r")\s*(?:\u0628\u0639\u062f|\u062f\u06cc\u06af\u0631)$"
)


def _day_number(text: str) -> int:
    """Map a matched day expression (word, digits, or «۱۵ام») to 1..31."""
    compact = text.replace(" ", "")
    if re.fullmatch(r"\d{1,2}", compact):
        return int(compact)
    if re.fullmatch(r"\d{1,2}\u0627\u0645", compact):
        return int(compact[:-2])
    day = _DAY_COMPACT.get(compact)
    if day is None:
        raise ValueError(f"unrecognized day: {text!r}")
    return day


def _next_month_day(month: int, day: int, now: float) -> float:
    """The next occurrence of (month, day) strictly after *now*.

    The year rolls forward until the date exists and is in the future.
    Esfand's 30th only exists in leap years, so the search is bounded by a
    leap cycle instead of assuming next year.
    """
    jy, _, _ = _timestamp_to_jalali(now)
    for year in range(jy, jy + 7):
        if day > _days_in_jalali_month(year, month):
            continue
        ts = _jalali_to_timestamp(year, month, day)
        if ts > now:
            return ts
    raise ValueError(
        f"\u00ab{day} {_month_name(month)}\u00bb has no valid date "
        "in the next six years"
    )


def _next_day_of_month(day: int, now: float) -> float:
    """The next occurrence of day-of-month in any month, strictly after *now*.

    «اول هر ماه» resolves to the first of the next month, «پانزدهم هر ماه»
    to the upcoming 15th wherever it falls. Months without the day (Esfand in
    common years has no 30th) are skipped, bounded by two leap cycles.
    """
    jy, jm, _ = _timestamp_to_jalali(now)
    for year in range(jy, jy + 2):
        start = jm if year == jy else 1
        for month in range(start, 13):
            if day > _days_in_jalali_month(year, month):
                continue
            ts = _jalali_to_timestamp(year, month, day)
            if ts > now:
                return ts
    raise ValueError(f"\u00ab{day} \u0647\u0631 \u0645\u0627\u0647\u00bb has no valid date soon")


def _try_relative(norm: str, now: float) -> float | None:
    """Resolve relative phrases like «فردا» or «سه روز بعد»."""
    today = datetime.date(*_timestamp_to_gregorian(now))
    midnight = _gregorian_to_timestamp(today.year, today.month, today.day)
    offsets = {
        "\u0627\u0645\u0631\u0648\u0632": 0,  # امروز
        "\u0641\u0631\u062f\u0627": 1,  # فردا
        "\u067e\u0633 \u0641\u0631\u062f\u0627": 2,  # پس فردا
        "\u067e\u0633\u0641\u0631\u062f\u0627": 2,  # پس‌فردا (no ZWNJ)
        "\u062f\u06cc\u0631\u0648\u0632": -1,  # دیروز
        "\u067e\u0631\u06cc\u0631\u0648\u0632": -2,  # پریروز
        "\u0647\u0641\u062a\u0647 \u0628\u0639\u062f": 7,  # هفته بعد
        "\u0647\u0641\u062a\u0647 \u0627\u06cc\u0646\u062f\u0647": 7,  # هفته آینده
    }
    if norm in offsets:
        return midnight + offsets[norm] * 86400
    if norm in (
        "\u0645\u0627\u0647 \u0628\u0639\u062f",
        "\u0645\u0627\u0647 \u0627\u06cc\u0646\u062f\u0647",
    ):
        # ماه بعد / ماه آینده
        return advance_due_date(now, None, 1)
    if norm in (
        "\u0633\u0627\u0644 \u0628\u0639\u062f",
        "\u0633\u0627\u0644 \u0627\u06cc\u0646\u062f\u0647",
    ):
        # سال بعد / سال آینده
        return advance_due_date(now, None, 12)
    if norm in (
        "\u0627\u062e\u0631 \u0645\u0627\u0647",
        "\u0627\u062e\u0631 \u0627\u06cc\u0646 \u0645\u0627\u0647",
    ):
        # آخر ماه / آخر این ماه
        jy, jm, _ = _timestamp_to_jalali(now)
        return _jalali_to_timestamp(jy, jm, _days_in_jalali_month(jy, jm))
    match = _RELATIVE_RE.match(norm)
    if match:
        number = _day_number(match.group("num"))
        unit = match.group("unit")
        if unit == "\u0631\u0648\u0632":  # روز
            return midnight + number * 86400
        if unit == "\u0647\u0641\u062a\u0647":  # هفته
            return midnight + number * 7 * 86400
        if unit == "\u0645\u0627\u0647":  # ماه
            return advance_due_date(now, None, number)
        if unit == "\u0633\u0627\u0644":  # سال
            return advance_due_date(now, None, number * 12)
    return None


def _try_month_day(norm: str, now: float) -> float | None:
    """Resolve «پانزدهم مهر», «۱۵ مهر ۱۴۰۴», «اول هر ماه»."""
    every_month = _EVERY_MONTH_RE.match(norm)
    if every_month:
        return _next_day_of_month(_day_number(every_month.group("day")), now)
    match = _MONTH_DAY_RE.match(norm)
    if not match:
        return None
    day = _day_number(match.group("day"))
    month = _MONTH_LOOKUP[match.group("month")]
    year_text = match.group("year")
    if year_text is not None:
        year = int(year_text)
        if year >= 1700:
            raise ValueError(
                f"year {year} is Gregorian; a Persian month needs a Jalali "
                f"year \u2014 try \u00ab15 {match.group('month')} "
                "\u06f1\u06f4\u06f0\u06f4\u00bb"
            )
        max_day = _days_in_jalali_month(year, month)
        if day > max_day:
            raise ValueError(
                f"\u00ab{day} {match.group('month')}\u00bb: "
                f"{match.group('month')} {year} has only {max_day} days"
            )
        return _jalali_to_timestamp(year, month, day)
    return _next_month_day(month, day, now)


def _try_weekday(norm: str, now: float) -> float | None:
    """Resolve «شنبه» (next occurrence) and «شنبه هفته آینده»."""
    match = _WEEKDAY_RE.match(norm)
    if not match:
        return None
    compact = match.group("day").replace(" ", "")
    target = _WEEKDAY_COMPACT.get(compact)
    if target is None:
        return None
    today = datetime.date(*_timestamp_to_gregorian(now))
    delta = (target - today.weekday()) % 7
    if delta == 0:
        delta = 7  # the named day means the next one, strictly after today
    if match.group("week") is not None:
        delta += 7
    target_date = today + datetime.timedelta(days=delta)
    return _gregorian_to_timestamp(target_date.year, target_date.month, target_date.day)


def parse_persian_date(text: str, now: float | None = None) -> float:
    """Resolve a natural Persian date phrase to a Unix timestamp.

    Phrases like «فردا», «پانزدهم مهر», «اول هر ماه» and «سه روز بعد»
    resolve to the midnight timestamp the scheduler already uses. The Jalali
    module stays the single source of calendar truth; this function only
    interprets words into dates. Ambiguous or unrecognized input raises
    ValueError with a worked example, never a guess.

    :param text: the phrase to resolve.
    :param now: reference instant for relative phrases; defaults to now.
    """
    if now is None:
        now = time.time()
    now = float(now)
    norm = normalize_fa(text).strip()
    if not norm:
        raise ValueError(f"unparseable date: {text!r}")
    resolved = _try_relative(norm, now)
    if resolved is None:
        resolved = _try_month_day(norm, now)
    if resolved is None:
        resolved = _try_weekday(norm, now)
    if resolved is not None:
        return resolved
    if norm in _MONTH_LOOKUP:
        raise ValueError(
            f"ambiguous date \u00ab{norm}\u00bb: a month without a day "
            f"\u2014 try \u00ab15 {norm}\u00bb"
        )
    if _DAY_ONLY_RE.match(norm):
        jy, jm, _ = _timestamp_to_jalali(now)
        example_month = _MONTHS[jm - 1][1]
        raise ValueError(
            f"ambiguous date \u00ab{norm}\u00bb: a day without a month "
            f"\u2014 try \u00ab{norm} {example_month}\u00bb"
        )
    raise ValueError(
        f"unrecognized date \u00ab{norm}\u00bb \u2014 try "
        "\u00ab\u0641\u0631\u062f\u0627\u00bb, \u00ab\u067e\u0627\u0646\u0632\u062f\u0647\u0645 "
        "\u0645\u0647\u0631\u00bb, or \u00ab\u0627\u0648\u0644 "
        "\u0647\u0631 \u0645\u0627\u0647\u00bb"
    )
