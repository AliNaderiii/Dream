"""Reminder tool stubs registered globally (bound at runtime to Dream instance)."""

from __future__ import annotations

from typing import Any

from dream.tools.base import tool


@tool(risk="guarded")
def create_reminder(
    date: str, text: str, repeat_days: int | None = None, repeat_months: int | None = None
) -> dict[str, Any]:
    """Create a durable reminder for the owner.

    The reminder fires on the given date and is stored per-owner.

    :param date: Due date as Jalali YYYY-MM-DD (year <1700) or a natural
        Persian phrase. Pure date only; time words cause refusal.
    :param text: Reminder text, what to remind about.
    :param repeat_days: Repeat every N days (optional).
    :param repeat_months: Repeat every N months (optional).
    """
    raise RuntimeError(
        "create_reminder requires a Dream instance; create a Dream first"
    )


@tool(risk="guarded")
def cancel_reminder(text: str, date: str | None = None) -> dict[str, Any]:
    """Cancel one of the owner's reminders, by text and an optional date.

    A row is removed only when the text and date identify exactly one
    active reminder; otherwise the tool refuses and names the candidates
    in Persian, touching nothing.

    :param text: Reminder text as the owner says it; a unique fragment is
        accepted.
    :param date: Optional due date as Jalali YYYY-MM-DD (year <1700) or a
        natural Persian phrase. Pure date only; time words cause refusal.
    """
    raise RuntimeError(
        "cancel_reminder requires a Dream instance; create a Dream first"
    )
