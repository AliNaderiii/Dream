"""Reminder matching, refusal/confirmation messages, and the prompt line.

The reminder tools live on the :class:`Dream` class (see
:mod:`dream.agent.dream`); the helpers here are pure functions of the
owner's stored reminders and the text they typed. The Persian
strings are kept as ``\\u`` escapes to match the existing convention
in :mod:`dream.reminders` and to survive any transit encoding.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from dream.memory import normalize_fa
from dream.reminders import (
    Reminder,
    format_jalali,
    parse_date_to_timestamp,
    parse_persian_date,
    prompt_reminders,
)

if TYPE_CHECKING:
    from dream.memory import MemoryStore

# Gloss: ساعت. A date argument containing the clock-time word is refused in
# both reminder tools; the date is a pure date, never a guessed hour.
_TIME_WORD = "\u0633\u0627\u0639\u062a"

# The create-side clock-time refusal, kept byte-identical to the M15 wording
# its tests pin. Gloss: «عبارت زمان «ساعت» در تاریخ پشتیبانی نمی‌شود؛ تاریخ را
# مثل «فردا» بفرست و ساعت را در متن یادآوری بنویس.»
_CREATE_TIME_HINT = (
    "\u0639\u0628\u0627\u0631\u062a \u0632\u0645\u0627\u0646 "
    "\u00ab\u0633\u0627\u0639\u062a\u00bb \u062f\u0631 "
    "\u062a\u0627\u0631\u06cc\u062e "
    "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc "
    "\u0646\u0645\u06cc\u0634\u0648\u062f\u061b "
    "\u062a\u0627\u0631\u06cc\u062e \u0631\u0627 "
    "\u0645\u062b\u0644 \u00ab\u0641\u0631\u062f\u0627\u00bb "
    "\u0628\u0641\u0631\u0633\u062a \u0648 "
    "\u0633\u0627\u0639\u062a \u0631\u0627 "
    "\u062f\u0631 \u0645\u062a\u0646 "
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u0628\u0646\u0648\u06cc\u0633."
)

# The cancel-side clock-time refusal. Gloss: «در date ساعت پشتیبانی نمی‌شود؛
# فقط تاریخ را مثل «فردا» یا «1405-05-19» بفرست.»
_CANCEL_TIME_HINT = (
    "\u062f\u0631 date "
    "\u0633\u0627\u0639\u062a "
    "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc "
    "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f\u061b "
    "\u0641\u0642\u0637 \u062a\u0627\u0631\u06cc\u062e "
    "\u0631\u0627 \u0645\u062b\u0644 "
    "\u00ab\u0641\u0631\u062f\u0627\u00bb \u06cc\u0627 "
    "\u00ab1405-05-19\u00bb "
    "\u0628\u0641\u0631\u0633\u062a."
)


def _resolve_reminder_date(date: str, time_hint: str) -> float:
    """Resolve a shared reminder-tool date argument, refusing clock times.

    Numeric input (``YYYY-MM-DD``; year below 1700 is Jalali) is tried first,
    then a natural Persian phrase; whatever neither parser accepts raises the
    parser's own message, and a clock-time word raises *time_hint*. Neither
    reminder tool ever guesses an hour.
    """
    date_norm = normalize_fa(date).strip()
    if not date_norm:
        raise ValueError(f"unparseable date: {date!r}")
    if _TIME_WORD in date_norm:
        raise ValueError(time_hint)
    try:
        return parse_date_to_timestamp(date_norm)
    except Exception:
        try:
            return parse_persian_date(date_norm)
        except Exception as exc:
            raise ValueError(str(exc)) from exc


def _match_reminders(store: MemoryStore, text: str) -> list[Reminder]:
    """Active reminders matching *text*: exact normalized, else substring.

    The owner speaks approximately («بیمه» for «تمدید بیمه ماشین»), so when
    no row equals the said text, rows merely containing it are candidates
    too. Removing is only allowed when exactly one row fits, and the
    confirmation always names the full stored text, so a shortened request
    can be verified against what was removed. Inactive reminders (fired
    one-offs) never enter matching.
    """
    query = normalize_fa(text).strip()
    active = store.list_reminders()
    exact = [rem for rem in active if normalize_fa(rem.text).strip() == query]
    if exact:
        return exact
    return [rem for rem in active if query in normalize_fa(rem.text)]


def _repeat_words(reminder: Reminder) -> str:
    """The repeat rule in Persian, or ``""`` for a one-off.

    Gloss of the phrasing: «هر روز» / «هر ۳ ماه».
    """
    if reminder.repeat_days is not None:
        if reminder.repeat_days == 1:
            return "\u0647\u0631 \u0631\u0648\u0632"  # هر روز
        return f"\u0647\u0631 {reminder.repeat_days} \u0631\u0648\u0632"  # هر N روز
    if reminder.repeat_months is not None:
        if reminder.repeat_months == 1:
            return "\u0647\u0631 \u0645\u0627\u0647"  # هر ماه
        return f"\u0647\u0631 {reminder.repeat_months} \u0645\u0627\u0647"  # هر N ماه
    return ""


def _candidate_summary(reminder: Reminder) -> str:
    """One candidate for a refusal list: text, Jalali date, repeat rule.

    The owner distinguishes two same-text reminders by the date he said; the
    Jalali date and the repeat rule make each candidate checkable.
    """
    due = format_jalali(reminder.due_at)
    repeat = _repeat_words(reminder)
    if repeat:
        return f"{reminder.text} ({due}\u060c {repeat})"  # ،
    return f"{reminder.text} ({due})"


def _candidates_summary(matches: list[Reminder]) -> str:
    """Join candidate summaries with the Persian semicolon separator."""
    return "\u061b ".join(_candidate_summary(rem) for rem in matches)


def _cancel_not_found_message(text: str) -> str:
    """Refusal when no active reminder fits *text*."""
    # Gloss: «یادآوری فعالی با متن «{text}» پیدا نشد؛ چیزی لغو نشد.»
    return (
        f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u0641\u0639\u0627\u0644\u06cc "
        f"\u0628\u0627 \u0645\u062a\u0646 \u00ab{text}\u00bb "
        f"\u067e\u06cc\u062f\u0627 \u0646\u0634\u062f\u061b "
        f"\u0686\u06cc\u0632\u06cc \u0644\u063a\u0648 "
        f"\u0646\u0634\u062f."
    )


def _cancel_ambiguous_message(text: str, matches: list[Reminder]) -> str:
    """Refusal asking the owner to choose between several candidates."""
    # Gloss: «چند یادآوری با متن «{text}» پیدا شد؛ کدام را لغو کنم؟ ...»
    return (
        f"\u0686\u0646\u062f \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u0628\u0627 \u0645\u062a\u0646 \u00ab{text}\u00bb "
        f"\u067e\u06cc\u062f\u0627 \u0634\u062f\u061b "
        f"\u06a9\u062f\u0627\u0645 \u0631\u0627 \u0644\u063a\u0648 "
        f"\u06a9\u0646\u0645\u061f "
        f"{_candidates_summary(matches)}"
    )


def _cancel_no_date_match_message(text: str, wanted: str, matches: list[Reminder]) -> str:
    """Refusal when the date filter empties the match."""
    # Gloss: «یادآوری فعالی با متن «{text}» برای تاریخ {date} پیدا نشد؛
    # چیزی لغو نشد. موارد موجود: ...»
    return (
        f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u0641\u0639\u0627\u0644\u06cc "
        f"\u0628\u0627 \u0645\u062a\u0646 \u00ab{text}\u00bb "
        f"\u0628\u0631\u0627\u06cc \u062a\u0627\u0631\u06cc\u062e {wanted} "
        f"\u067e\u06cc\u062f\u0627 \u0646\u0634\u062f\u061b "
        f"\u0686\u06cc\u0632\u06cc \u0644\u063a\u0648 \u0646\u0634\u062f. "
        f"\u0645\u0648\u0627\u0631\u062f "
        f"\u0645\u0648\u062c\u0648\u062f: "
        f"{_candidates_summary(matches)}"
    )


def _cancelled_message(reminder: Reminder) -> str:
    """The Persian confirmation naming what was removed, in Jalali."""
    # Gloss: «یادآوری «{text}» برای {due} (تکرار: ...) لغو شد.»
    due = format_jalali(reminder.due_at)
    repeat = _repeat_words(reminder)
    if repeat:
        return (
            f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
            f"\u00ab{reminder.text}\u00bb "
            f"\u0628\u0631\u0627\u06cc {due} "
            f"(\u062a\u06a9\u0631\u0627\u0631: {repeat}) "
            f"\u0644\u063a\u0648 \u0634\u062f."
        )
    return (
        f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u00ab{reminder.text}\u00bb "
        f"\u0628\u0631\u0627\u06cc {due} \u0644\u063a\u0648 \u0634\u062f."
    )


def _relative_age(timestamp: float) -> str:
    """Render a memory's age as ``"today"`` / ``"1 day ago"`` / ``"N days ago"``."""
    days = max(0, int((time.time() - timestamp) // 86400))
    if days == 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _render_reminder_line(reminder: Reminder) -> str:
    """Render one reminder for the prompt: text plus its stored Jalali date.

    The date is the owner's own record, so it is explicit on the line and the
    model repeats it instead of guessing. A past due date is flagged with
    «دیر شده» so the model can tell the owner the deadline has passed.
    """
    date = format_jalali(reminder.due_at)
    if reminder.due_at <= time.time():
        return (
            f"- {reminder.text} "
            f"(\u0633\u0631\u0631\u0633\u06cc\u062f {date} \u2014 "
            f"\u062f\u06cc\u0631 \u0634\u062f\u0647)"
        )
    return f"- {reminder.text} (\u0633\u0631\u0631\u0633\u06cc\u062f {date})"


# Re-export the prompt_reminders function for convenience so callers of this
# module do not need to also import from dream.reminders.
__all__ = [
    "Reminder",
    "_CANCEL_TIME_HINT",
    "_CREATE_TIME_HINT",
    "_TIME_WORD",
    "_candidate_summary",
    "_candidates_summary",
    "_cancel_ambiguous_message",
    "_cancel_not_found_message",
    "_cancel_no_date_match_message",
    "_cancelled_message",
    "_match_reminders",
    "_relative_age",
    "_render_reminder_line",
    "_repeat_words",
    "_resolve_reminder_date",
    "format_jalali",
    "parse_date_to_timestamp",
    "parse_persian_date",
    "prompt_reminders",
]
