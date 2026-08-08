"""Pin the clock tool shape seen by Persian reminder replies.

The measured defect was not a wrong reminder: the stored Jalali date reached the
reply, but an ISO 8601 clock-tool result was copied ahead of the Persian
sentence. These tests make a scripted conversation echo the tool result so the
raw machine timestamp shape fails visibly if it returns.
"""

from __future__ import annotations

import re
from datetime import datetime

from dream.agent import Dream
from dream.memory import MemoryStore
from dream.reminders import parse_date_to_timestamp

_OIL_TEXT = "\u062a\u0639\u0648\u06cc\u0636 \u0631\u0648\u063a\u0646 \u0645\u0627\u0634\u06cc\u0646"
_OIL_QUESTION = (
    "\u06a9\u06cc \u0628\u0627\u06cc\u062f \u0631\u0648\u063a\u0646 "
    "\u0645\u0627\u0634\u06cc\u0646 \u0631\u0627 \u0639\u0648\u0636 "
    "\u06a9\u0646\u0645\u061f"
)
_OIL_REPLY = (
    "\u0631\u0648\u063a\u0646 \u0645\u0627\u0634\u06cc\u0646 \u062f\u0631 "
    "\u062a\u0627\u0631\u06cc\u062e {date} \u0633\u0631\u0631\u0633\u06cc\u062f "
    "\u062f\u0627\u0631\u062f."
)
_LATIN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 8, 16, 8, 1, 523609, tzinfo=tz)


class _ToolEchoingReminderBackend:
    def chat(self, messages, tools=None):
        if tools is None:
            return {"content": "[]", "tool_calls": []}
        if messages[-1].get("role") == "tool":
            tool_text = str(messages[-1].get("content", ""))
            system_text = str(messages[0].get("content", ""))
            match = re.search(r"1405-12-01", system_text)
            date = match.group(0) if match else "missing-date"
            return {"content": f"{tool_text} {_OIL_REPLY.format(date=date)}", "tool_calls": []}
        return {
            "content": None,
            "tool_calls": [{"id": "clock", "name": "get_datetime", "arguments": {}}],
        }


def test_persian_dated_reminder_reply_does_not_expose_clock_machine_shape(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("dream.tools.datetime", _FixedDatetime)
    store = MemoryStore(str(tmp_path / "clock-reminder.db"))
    try:
        store.add_reminder(_OIL_TEXT, parse_date_to_timestamp("1405-12-01"))
        turn = Dream(store, _ToolEchoingReminderBackend()).run(_OIL_QUESTION)
    finally:
        store.close()

    assert "1405-12-01" in turn.reply
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", turn.reply), turn.reply
    assert not re.search(r"[+-]\d{2}:\d{2}", turn.reply), turn.reply
    for month in _LATIN_MONTHS:
        assert month not in turn.reply
