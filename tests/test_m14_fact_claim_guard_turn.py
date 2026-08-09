"""Pins M14's fact save-claim guard at the turn seam: what the owner sees.

What this pins and what evidence justified it:

- On merged main the skill guard covers skills only, so a reply claiming a
  fact was remembered or stored reaches the owner unguarded even when no
  memory row was written. These tests pin that a finished turn whose reply
  claims a fact write with no row anywhere must show the owner a Persian
  warning, and that the two truthful roads are untouched byte for byte:

  * the extraction road — the silent pass writes the fact after the reply is
    composed, the call list is empty, and the row is on the turn; no warning.
  * the tool road — ``remember_fact`` wrote the row; no warning.

- The abandoned-extraction boundary is pinned here: when the pass has not
  finished by the time the reply goes out, the guard does nothing, because a
  truthful reply can be composed before its own row exists.

- The mixed sentence (skill claim plus fact claim) yields exactly one warning;
  the reminder/procedure collision sentence fires neither guard and stays put.

This module deliberately defines its own warning constant and imports nothing
new from the source's guard machinery, so against unchanged source the
assertions fail with a message naming the problem — the owner would see the
raw unguarded claim — not with an import error. The detector's unit tests
live in test_m14_fact_claim_guard.py and are red by the guard module not
existing there.
"""

from __future__ import annotations

import json
import time

import pytest

from dream.agent import Dream
from dream.extraction import STATUS_ABANDONED, STATUS_FACTS_FOUND, STATUS_NO_FACTS
from dream.memory import MemoryStore

# Gloss: این را در حافظه ذخیره کردم.
CLAIM_HAFEZE = (
    "\u0627\u06cc\u0646 \u0631\u0627 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 "
    "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0631\u062f\u0645"
)
# Gloss: این واقعیت ثبت شد.
CLAIM_SABT = (
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u062b\u0628\u062a \u0634\u062f"
)
# Gloss: یادم می‌ماند که شما مهندس هستید.
CLAIM_RECALL = (
    "\u06cc\u0627\u062f\u0645 \u0645\u06cc\u200c\u0645\u0627\u0646\u062f \u06a9\u0647 "
    "\u0634\u0645\u0627 \u0645\u0647\u0646\u062f\u0633 \u0647\u0633\u062a\u06cc\u062f"
)
# Gloss: سگ من اسمش رکس است (a user message carrying a groundable fact).
USER_PET = "\u0633\u06af \u0645\u0646 \u0627\u0633\u0645\u0634 \u0631\u06a9\u0633 \u0627\u0633\u062a"  # noqa: E501
# Gloss: سگ کاربر رکس است (the fact the extraction pass returns, grounded in
# the user message by the shared stems سگ and رکس).
EXTRACT_PET = "\u0633\u06af \u06a9\u0627\u0631\u0628\u0631 \u0631\u06a9\u0633 \u0627\u0633\u062a"
# Gloss: کاربر مهندس است (a memory the model can truthfully recall).
MEM_ENGINEER = "\u06a9\u0627\u0631\u0628\u0631 \u0645\u0647\u0646\u062f\u0633 \u0627\u0633\u062a"
# Gloss: من مهندس هستم (a user message that recalls the engineer memory).
USER_ENGINEER = "\u0645\u0646 \u0645\u0647\u0646\u062f\u0633 \u0647\u0633\u062a\u0645"
# Gloss: در مورد هوا به من بگو (a user message with no extractable fact).
USER_WEATHER = "\u062f\u0631 \u0645\u0648\u0631\u062f \u0647\u0648\u0627 \u0628\u0647 \u0645\u0646 \u0628\u06af\u0648"  # noqa: E501
# Gloss: این روش در فایل ذخیره شد و این واقعیت در حافظه ثبت شد (mixed sentence).
MIXED_BOTH = (
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u062f\u0631 \u0641\u0627\u06cc\u0644 \u0630\u062e\u06cc\u0631\u0647 "  # noqa: E501
    "\u0634\u062f \u0648 \u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u062f\u0631 "
    "\u062d\u0627\u0641\u0638\u0647 \u062b\u0628\u062a \u0634\u062f"
)
# Gloss: یادآوری روش تمدید بیمه تنظیم شد (the brief's collision sentence).
MIXED_BRIEF = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f "
    "\u0628\u06cc\u0645\u0647 \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f"
)

# The fact warning the owner must see. Gloss: توجه: ادعای ذخیره‌شدن این واقعیت
# تایید نشده است؛ چیزی در حافظه ذخیره نشده است.
FACT_WARNING = (
    "\n\n"
    "\u062a\u0648\u062c\u0647: "
    "\u0627\u062f\u0639\u0627\u06cc \u0630\u062e\u06cc\u0631\u0647\u200c\u0634\u062f\u0646 "
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a "
    "\u062a\u0627\u06cc\u06cc\u062f \u0646\u0634\u062f\u0647 \u0627\u0633\u062a\u061b "
    "\u0686\u06cc\u0632\u06cc \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
)
# The skill warning, for the single-warning assertion. Gloss: توجه: ادعای
# ذخیره‌شدن این روش تایید نشده است؛ فایل همان روش تغییر نکرده است.
SKILL_WARNING = (
    "\n\n"
    "\u062a\u0648\u062c\u0647: "
    "\u0627\u062f\u0639\u0627\u06cc \u0630\u062e\u06cc\u0631\u0647\u200c\u0634\u062f\u0646 "
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 "
    "\u062a\u0627\u06cc\u06cc\u062f \u0646\u0634\u062f\u0647 \u0627\u0633\u062a\u061b "
    "\u0641\u0627\u06cc\u0644 \u0647\u0645\u0627\u0646 \u0631\u0648\u0634 "
    "\u062a\u063a\u06cc\u06cc\u0631 \u0646\u06a9\u0631\u062f\u0647 \u0627\u0633\u062a."
)


class ScriptedBackend:
    """Deterministic model: scripted tool calls, then a fixed final reply.

    The extraction pass calls ``chat`` with ``tools=None``; those requests
    return ``extraction`` (a JSON fact batch, or "[]" for none).
    """

    def __init__(self, reply: str, calls: list[dict] | None = None, extraction: str = "[]") -> None:
        self._reply = reply
        self._calls = list(calls or [])
        self._extraction = extraction
        self._index = 0

    def chat(self, messages, tools=None):
        if tools is None:
            return {"content": self._extraction, "tool_calls": []}
        if self._index < len(self._calls):
            call = self._calls[self._index]
            self._index += 1
            return {
                "content": None,
                "tool_calls": [{"id": f"call-{self._index}", **call}],
            }
        return {"content": self._reply, "tool_calls": []}


class HangingExtractionBackend:
    """Conversation replies instantly; extraction never answers in budget."""

    def __init__(self, reply: str, hang_seconds: float) -> None:
        self._reply = reply
        self._hang_seconds = hang_seconds

    def chat(self, messages, tools=None):
        if tools is not None:
            return {"content": self._reply, "tool_calls": []}
        time.sleep(self._hang_seconds)
        return {"content": "[]", "tool_calls": []}


@pytest.fixture()
def store(tmp_path):
    memory_store = MemoryStore(str(tmp_path / "dream.db"))
    yield memory_store
    memory_store.close()


def _remember_fact_call(content: str) -> dict:
    return {"name": "remember_fact", "arguments": {"content": content}}


def _extraction_payload(fact: str) -> str:
    return json.dumps(
        [{"content": fact, "kind": "semantic", "importance": 0.5}],
        ensure_ascii=False,
    )


def test_extraction_road_truthful_fact_reply_is_not_warned(store):
    """The silent extraction pass wrote the row with an empty call list; the
    reply claiming the save must not be warned, and the row is printed."""
    payload = _extraction_payload(EXTRACT_PET)
    backend = ScriptedBackend(reply=CLAIM_HAFEZE, extraction=payload)
    turn = Dream(store, backend).run(USER_PET)

    assert turn.reply == CLAIM_HAFEZE, f"truthful extraction reply must be untouched: {turn.reply!r}"  # noqa: E501
    assert turn.tool_calls == []
    assert turn.extraction.status == STATUS_FACTS_FOUND
    assert len(turn.memories_created) == 1, "the extraction pass wrote one row"
    row = turn.memories_created[0]
    print(f"[extraction-road row] id={row.id} content={row.content!r} source={row.source}")
    assert row.content == EXTRACT_PET
    assert FACT_WARNING not in turn.reply


def test_tool_road_truthful_fact_reply_is_not_warned(store):
    """A remember_fact call wrote the row; the reply is untouched byte for byte."""
    backend = ScriptedBackend(
        reply=CLAIM_HAFEZE,
        calls=[_remember_fact_call(MEM_ENGINEER)],
        extraction="[]",
    )
    turn = Dream(store, backend).run(USER_PET)

    assert turn.reply == CLAIM_HAFEZE, f"truthful tool reply must be byte-identical: {turn.reply!r}"
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0]["name"] == "remember_fact"
    assert turn.tool_calls[0]["allowed"] is True
    assert len(turn.memories_created) == 1
    print(f"[tool-road row] id={turn.memories_created[0].id} "
          f"content={turn.memories_created[0].content!r}")
    assert FACT_WARNING not in turn.reply


def test_fact_reply_with_no_row_anywhere_is_warned(store):
    """A claim with no tool call, no extraction row, and nothing recalled is a
    lie: the owner must see the warning, not the raw claim."""
    backend = ScriptedBackend(reply=CLAIM_SABT, extraction="[]")
    turn = Dream(store, backend).run(USER_WEATHER)

    assert turn.reply == CLAIM_SABT + FACT_WARNING, (
        "owner must see the unconfirmed-claim warning; "
        f"got: {turn.reply!r}"
    )
    assert turn.extraction.status == STATUS_NO_FACTS
    assert turn.memories_created == []
    assert FACT_WARNING in turn.reply


def test_truthful_recall_of_an_injected_memory_is_not_warned(store):
    """«یادم می‌ماند که شما مهندس هستید» backed by a memory the model was shown
    is a truthful recall, not a claim of a fresh write — it is untouched."""
    store.remember(MEM_ENGINEER)
    backend = ScriptedBackend(reply=CLAIM_RECALL, extraction="[]")
    turn = Dream(store, backend).run(USER_ENGINEER)

    assert turn.reply == CLAIM_RECALL, f"truthful recall must be untouched: {turn.reply!r}"
    assert any(m.content == MEM_ENGINEER for m in (turn.memories_injected or []))
    assert FACT_WARNING not in turn.reply


def test_abandoned_extraction_does_not_warn(store, monkeypatch):
    """When extraction is abandoned the guard does nothing: a truthful reply
    can be composed before its own row exists because the pass runs on a
    worker with a wall-clock budget. Warning then would punish truth."""
    monkeypatch.setenv("DREAM_EXTRACTION_TIMEOUT_SECONDS", "0.3")
    backend = HangingExtractionBackend(reply=CLAIM_HAFEZE, hang_seconds=3.0)
    turn = Dream(store, backend).run(USER_PET)

    assert turn.extraction.status == STATUS_ABANDONED
    assert turn.reply == CLAIM_HAFEZE, (
        "an abandoned extraction must not turn a truthful reply into a lie; "
        f"got: {turn.reply!r}"
    )
    assert FACT_WARNING not in turn.reply


def test_mixed_sentence_gets_exactly_one_warning(store):
    """A sentence naming both a skill-file claim and a fact claim yields exactly
    one warning (the skill guard owns it); the fact warning is not appended."""
    backend = ScriptedBackend(reply=MIXED_BOTH, extraction="[]")
    turn = Dream(store, backend).run(USER_WEATHER)

    assert turn.reply == MIXED_BOTH + SKILL_WARNING, (
        "exactly the skill warning, never two; "
        f"got: {turn.reply!r}"
    )
    assert FACT_WARNING not in turn.reply


def test_reminder_procedure_collision_sentence_is_unchanged(store):
    """The brief's mixed reminder/procedure sentence fires neither guard
    (reminders are a deferred tool), so it reaches the owner with no warning."""
    backend = ScriptedBackend(reply=MIXED_BRIEF, extraction="[]")
    turn = Dream(store, backend).run(USER_WEATHER)

    assert turn.reply == MIXED_BRIEF, (
        "the reminder/procedure collision must not double-warn; "
        f"got: {turn.reply!r}"
    )
    assert FACT_WARNING not in turn.reply
