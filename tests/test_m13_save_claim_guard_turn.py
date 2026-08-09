"""Pins M13's save-claim guard at the turn seam: what the owner sees.

What this pins and what evidence justified it:

- The owner was once told the second half of a procedure was added while the
  file on disk still held one step: the reply claimed a save, no save_skill
  call happened, and nothing enforced the M11 prompt sentence. These tests
  pin that a finished turn whose reply claims a skill save without a
  completed save_skill call must show the owner a Persian warning, and that
  a truthful turn — a claim backed by a completed save — reaches the owner
  byte for byte.

- This module deliberately imports nothing new from the source: against
  unchanged source its assertions fail with a message naming the problem
  (the owner would see the raw unguarded claim), not with an import error.
  The detector's unit tests live in test_m13_save_claim_guard.py and are
  red by the guard functions not existing there.

- The scripted backend is deterministic: it emits the scripted tool calls
  (or none), then the fixed reply; extraction requests (tools=None) return
  an empty batch so no durable fact disturbs the assertion. Every new test
  was observed red against unchanged source and green after the source
  change (messages in the PR).
"""

from __future__ import annotations

import json

import pytest

from dream import tools as dream_tools
from dream.agent import Dream
from dream.memory import MemoryStore

# Gloss: روش تمدید بیمه ماشین ذخیره شد.
CLAIM = (
    "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "
    "\u0645\u0627\u0634\u06cc\u0646 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
)
# Gloss: تمدید بیمه ماشین | قدم اول
NAME = "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
STEP = "\u0642\u062f\u0645 \u0627\u0648\u0644"
# Gloss: یاد بگیر: اول بیمه‌نامه قبلی را پیدا می‌کنم
USER_MSG = (
    "\u06cc\u0627\u062f \u0628\u06af\u06cc\u0631: \u0627\u0648\u0644 \u0628\u06cc\u0645\u0647\u200c\u0646\u0627\u0645\u0647 "  # noqa: E501
    "\u0642\u0628\u0644\u06cc \u0631\u0627 \u067e\u06cc\u062f\u0627 \u0645\u06cc\u200c\u06a9\u0646\u0645"  # noqa: E501
)
# The warning the owner must see when the claim is unconfirmed.
# Gloss: توجه: ادعای ذخیره‌شدن این روش تایید نشده است؛ فایل همان روش تغییر نکرده است.
WARNING = (
    "\n\n"
    "\u062a\u0648\u062c\u0647: \u0627\u062f\u0639\u0627\u06cc \u0630\u062e\u06cc\u0631\u0647\u200c\u0634\u062f\u0646 "  # noqa: E501
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u062a\u0627\u06cc\u06cc\u062f \u0646\u0634\u062f\u0647 \u0627\u0633\u062a\u061b "  # noqa: E501
    "\u0641\u0627\u06cc\u0644 \u0647\u0645\u0627\u0646 \u0631\u0648\u0634 \u062a\u063a\u06cc\u06cc\u0631 "  # noqa: E501
    "\u0646\u06a9\u0631\u062f\u0647 \u0627\u0633\u062a."
)


class ScriptedBackend:
    """Deterministic model: scripted tool calls, then a fixed final reply.

    The extraction pass calls ``chat`` with ``tools=None``; those requests
    return an empty JSON batch so no durable fact is written.
    """

    def __init__(self, calls: list[dict], reply: str) -> None:
        self._calls = list(calls)
        self._reply = reply
        self._index = 0

    def chat(self, messages, tools=None):
        if tools is None:
            return {"content": "[]", "tool_calls": []}
        if self._index < len(self._calls):
            call = self._calls[self._index]
            self._index += 1
            return {
                "content": None,
                "tool_calls": [{"id": f"call-{self._index}", **call}],
            }
        return {"content": self._reply, "tool_calls": []}


@pytest.fixture()
def store(tmp_path):
    memory_store = MemoryStore(str(tmp_path / "dream.db"))
    yield memory_store
    memory_store.close()


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(dream_tools, "WORKSPACE_ROOT", tmp_path.resolve())
    return tmp_path.resolve()


def _save_call() -> dict:
    return {
        "name": "save_skill",
        "arguments": {"name": NAME, "description": "d", "steps": [STEP]},
    }


def test_owner_sees_a_warning_when_a_save_claim_has_no_call(workspace, store):
    """The observed failure shape: a claimed save with no save_skill call.
    The owner must not be left believing the file changed."""
    backend = ScriptedBackend([], CLAIM)
    turn = Dream(store, backend).run(USER_MSG)

    assert turn.reply == CLAIM + WARNING, (
        "owner must see the unconfirmed-claim warning, not the raw claim; "
        f"got: {turn.reply!r}"
    )
    assert turn.tool_calls == []
    assert WARNING in turn.reply


def test_truthful_claim_reply_is_untouched_byte_for_byte(workspace, store):
    """A claim backed by a completed save_skill call ships unchanged."""
    backend = ScriptedBackend([_save_call()], CLAIM)
    turn = Dream(store, backend).run(USER_MSG)

    assert turn.reply == CLAIM, f"truthful reply must be byte-identical: {turn.reply!r}"
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0]["name"] == "save_skill"
    assert turn.tool_calls[0]["allowed"] is True
    payload = json.loads(turn.tool_calls[0]["result"])
    assert payload["status"] == "ok"
    assert (workspace / "skills" / f"{NAME}.txt").exists()


def test_truthful_reply_stays_unchanged_after_a_warning_turn(workspace, store):
    """Two turns in one session: a false claim gets the warning, a later true
    claim on the same conversation is still untouched."""
    dream = Dream(store, ScriptedBackend([], CLAIM))
    first = dream.run(USER_MSG)
    assert first.reply == CLAIM + WARNING

    dream.backend = ScriptedBackend([_save_call()], CLAIM)
    second = dream.run(USER_MSG)
    assert second.reply == CLAIM
    assert (workspace / "skills" / f"{NAME}.txt").exists()
