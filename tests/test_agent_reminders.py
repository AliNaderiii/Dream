"""Pin that scheduled reminders reach the model prompt (M1).

Measured problem: the owner asked when to change the car oil while Dream held
a dated reminder for exactly that, and the model answered from general
knowledge about mileage. `grep -c -i remind dream/agent.py` returned zero:
the agent module never saw reminders. These tests pin the fix — reminders are
searched with the query the way memories are, anything due soon is included
regardless of the query, the stored Jalali date is what the model sees, and
the reminder section shares the existing block character budget without ever
crowding memories out.

New Persian strings in this module are written as backslash-u escapes,
matching tests/test_extraction_prompt.py, so they cannot be corrupted in
transit.
"""

from __future__ import annotations

import time

import pytest

from dream.agent import (
    _MEMORIES_CLOSE,
    _MEMORIES_OPEN,
    _REMINDER_USAGE,
    _REMINDERS_CLOSE,
    _REMINDERS_OPEN,
    Dream,
    EchoBackend,
)
from dream.memory import MemoryStore
from dream.reminders import (
    MAX_REMINDER_LINES,
    format_jalali,
    parse_date_to_timestamp,
    prompt_reminders,
)

# Persian strings as \u escapes (inline glosses in plain text):
# یادآوریها (reminders), پایان (end), سررسید (due date), دیر شده (overdue),
# تعویض روغن ماشین (car oil change), پرداخت قسط وام (loan instalment),
# خرید هدیه تولد (birthday gift), کاربر قهوه تلخ دوست دارد (the user likes
# bitter coffee), کی باید روغن ماشین را عوض کنم؟ (when should I change the
# car oil?), هوا چطور است؟ (how is the weather?), قهوه دوست داری؟ (do you
# like coffee?), پاسخ. (a reply), روغن ماشین (car oil).
_T_OIL = "\u062a\u0639\u0648\u06cc\u0636 \u0631\u0648\u063a\u0646 \u0645\u0627\u0634\u06cc\u0646"
_Q_OIL = (
    "\u06a9\u06cc \u0628\u0627\u06cc\u062f \u0631\u0648\u063a\u0646 \u0645\u0627\u0634\u06cc\u0646 "
    "\u0631\u0627 \u0639\u0648\u0636 \u06a9\u0646\u0645\u061f"
)
_Q_WEATHER = "\u0647\u0648\u0627 \u0686\u0637\u0648\u0631 \u0627\u0633\u062a\u061f"
_T_LOAN = "\u067e\u0631\u062f\u0627\u062e\u062a \u0642\u0633\u0637 \u0648\u0627\u0645"
_T_GIFT = "\u062e\u0631\u06cc\u062f \u0647\u062f\u06cc\u0647 \u062a\u0648\u0644\u062f"
_M_COFFEE = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0642\u0647\u0648\u0647 "
    "\u062a\u0644\u062e \u062f\u0648\u0633\u062a \u062f\u0627\u0631\u062f"
)
_Q_COFFEE = "\u0642\u0647\u0648\u0647 \u062f\u0648\u0633\u062a \u062f\u0627\u0631\u06cc\u061f"
_REPLY = "\u067e\u0627\u0633\u062e."
_OVERDUE = "\u062f\u06cc\u0631 \u0634\u062f\u0647"
_DUE_WORD = "\u0633\u0631\u0631\u0633\u06cc\u062f"


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "agent-reminders.db"))
    yield s
    s.close()


def _due(jy, jm, jd):
    return parse_date_to_timestamp(f"{jy:04d}-{jm:02d}-{jd:02d}")


class CaptureBackend(EchoBackend):
    """Records the system prompt the agent sends, then replies in Persian."""

    def __init__(self):
        self.system_prompt = ""

    def chat(self, messages, tools=None):
        if tools is not None:
            self.system_prompt = messages[0]["content"]
        return {"content": _REPLY, "tool_calls": []}


# --------------------------------------------------------------------------
# M1 acceptance: the oil question reaches the stored date
# --------------------------------------------------------------------------


def test_oil_reminder_date_reaches_the_model(store, monkeypatch):
    """The measured M1 problem: the oil reminder is in the system prompt."""
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    due = _due(1405, 8, 15)
    store.add_reminder(_T_OIL, due)

    backend = CaptureBackend()
    turn = Dream(store, backend).run(_Q_OIL)

    assert _REMINDERS_OPEN in backend.system_prompt
    assert _REMINDERS_CLOSE in backend.system_prompt
    assert _T_OIL in backend.system_prompt
    assert format_jalali(due) in backend.system_prompt
    assert _DUE_WORD in backend.system_prompt
    assert turn.reply == _REPLY  # the reply path still works


def test_query_with_no_reminder_leaves_the_prompt_unchanged(store, monkeypatch):
    """No reminders: the prompt is byte-for-byte what it was before M1."""
    monkeypatch.setenv("DREAM_EXTRACTION", "off")

    backend = CaptureBackend()
    Dream(store, backend).run(_Q_WEATHER)

    assert _REMINDERS_OPEN not in backend.system_prompt
    assert _REMINDER_USAGE not in backend.system_prompt
    # Empty memory section closes the prompt exactly as before.
    assert backend.system_prompt.endswith(f"{_MEMORIES_OPEN}\n{_MEMORIES_CLOSE}")


def test_unrelated_far_future_reminder_stays_out(store, monkeypatch):
    """A reminder neither relevant nor due soon is not surfaced."""
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    store.add_reminder(_T_GIFT, time.time() + 200 * 86400)

    backend = CaptureBackend()
    Dream(store, backend).run(_Q_WEATHER)

    assert _T_GIFT not in backend.system_prompt
    assert _REMINDERS_OPEN not in backend.system_prompt


def test_due_soon_reminder_reaches_the_model_regardless_of_query(store, monkeypatch):
    """Anything due within the soon window appears even with no word overlap."""
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    store.add_reminder(_T_LOAN, time.time() + 2 * 86400)

    backend = CaptureBackend()
    Dream(store, backend).run(_Q_WEATHER)

    assert _T_LOAN in backend.system_prompt
    assert _REMINDERS_OPEN in backend.system_prompt


def test_overdue_reminder_is_marked_overdue_in_the_prompt(store, monkeypatch):
    """A past due date is flagged so the model tells the owner it is late."""
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    store.add_reminder(_T_OIL, time.time() - 3600)

    backend = CaptureBackend()
    Dream(store, backend).run(_Q_OIL)

    assert _DUE_WORD in backend.system_prompt
    assert _OVERDUE in backend.system_prompt


def test_arabic_yeh_spelling_of_the_query_still_finds_the_reminder(store, monkeypatch):
    """Persian-specialist adversarial pass: Arabic yeh everywhere must match.

    The reminder is stored with Farsi yeh; the query uses Arabic yeh
    (كي بايد ... ماشين ... كنم). normalise_fa folds both, so the reminder
    must still surface.
    """
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    due = _due(1405, 8, 15)
    store.add_reminder(_T_OIL, due)
    question_arabic_yeh = (
        "\u0643\u064a \u0628\u0627\u064a\u062f \u0631\u0648\u063a\u0646 "
        "\u0645\u0627\u0634\u064a\u0646 \u0631\u0627 \u0639\u0648\u0636 "
        "\u0643\u0646\u0645\u061f"
    )

    backend = CaptureBackend()
    Dream(store, backend).run(question_arabic_yeh)

    assert _T_OIL in backend.system_prompt
    assert format_jalali(due) in backend.system_prompt


def test_reminders_never_crowd_out_memories(store, monkeypatch):
    """The shared budget is filled by memories first; reminders fit the rest."""
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    store.remember(_M_COFFEE, kind="semantic")
    # A due-soon reminder that qualifies regardless of the query.
    store.add_reminder(_T_LOAN, time.time() + 2 * 86400)
    line = f"- [today] {_M_COFFEE}"
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", str(len(line)))

    backend = CaptureBackend()
    Dream(store, backend).run(_Q_COFFEE)

    assert _M_COFFEE in backend.system_prompt
    assert _REMINDERS_OPEN not in backend.system_prompt
    assert _T_LOAN not in backend.system_prompt


# --------------------------------------------------------------------------
# Selection: prompt_reminders ranking
# --------------------------------------------------------------------------


def test_prompt_reminders_includes_relevant_and_due_soon_only(store):
    """Relevant and due-soon reminders are chosen; far-future unrelated are not."""
    store.add_reminder(_T_LOAN, time.time() + 2 * 86400)  # due soon
    store.add_reminder(_T_OIL, _due(1405, 8, 15))  # relevant to the query
    store.add_reminder(_T_GIFT, time.time() + 200 * 86400)  # neither

    chosen = prompt_reminders(store.list_reminders(), _Q_OIL)

    texts = [reminder.text for reminder in chosen]
    assert _T_OIL in texts  # relevant
    assert _T_LOAN in texts  # due soon, regardless of the query
    assert _T_GIFT not in texts  # far future and unrelated


def test_prompt_reminders_ranks_the_matching_reminder_first(store):
    """Relevance dominates the urgency bonus: the oil reminder leads."""
    store.add_reminder(_T_LOAN, time.time() + 2 * 86400)  # urgency 0.5
    store.add_reminder(_T_OIL, _due(1405, 8, 15))  # relevance ~0.67

    chosen = prompt_reminders(store.list_reminders(), _Q_OIL)

    assert chosen[0].text == _T_OIL


def test_prompt_reminders_respects_the_line_limit(store):
    """More qualifying reminders than the cap still yield at most five."""
    for index in range(9):
        store.add_reminder(f"task number {index}", time.time() + 86400)

    chosen = prompt_reminders(store.list_reminders(), "task")

    assert 0 < len(chosen) <= MAX_REMINDER_LINES


def test_prompt_reminders_empty_and_zero_limit(store):
    """No reminders or a zero limit select nothing and never raise."""
    assert prompt_reminders([], _Q_WEATHER) == []
    store.add_reminder(_T_LOAN, time.time() + 86400)
    assert prompt_reminders(store.list_reminders(), "task", limit=0) == []
