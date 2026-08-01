"""Tests for the system prompt, the recalled-memory block, and commands.

The extraction pass writes memory on its own, so the prompt's memory job is
no longer teaching the model to store — it is making the model *use* what
the store recalls: treat the memories as true, use them naturally without
announcing it, and answer straight from them when they already hold the
answer. These tests pin that instruction, the all-Persian memory-block
markers, the unconditional language rule, and the backslash command aliases.
Everything runs offline against EchoBackend or scripted mocks — no network.

New Persian strings in this module are written as backslash-u escapes,
matching tests/test_extraction_prompt.py, so they cannot be corrupted in
transit; strings predating that rule are left as written.
"""

from __future__ import annotations

import re

import pytest

import cli
from dream.agent import _MEMORIES_CLOSE, _MEMORIES_OPEN, Dream, EchoBackend
from dream.memory import MemoryStore

# The memory-block markers as they must appear, written as \u escapes:
# [خاطره‌های بازیابی‌شده — زمینه خصوصی] and [پایان خاطره‌ها].
_OPEN = (
    "[\u062e\u0627\u0637\u0631\u0647\u200c\u0647\u0627\u06cc "
    "\u0628\u0627\u0632\u06cc\u0627\u0628\u06cc\u200c\u0634\u062f\u0647 \u2014 "
    "\u0632\u0645\u06cc\u0646\u0647 \u062e\u0635\u0648\u0635\u06cc]"
)
_CLOSE = "[\u067e\u0627\u06cc\u0627\u0646 \u062e\u0627\u0637\u0631\u0647\u200c\u0647\u0627]"

# The reported turn's two stored facts and its question, as escapes:
# کاربر علی نام دارد / کاربر روی استارتاپ فین‌تک کار می‌کند / کجا کار می‌کنم؟
_FACT_ALI = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc "
    "\u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
)
_FACT_FINTECH = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0648\u06cc "
    "\u0627\u0633\u062a\u0627\u0631\u062a\u0627\u067e \u0641\u06cc\u0646\u200c\u062a\u06a9 "
    "\u06a9\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u062f"
)
_ASK_WORK = "\u06a9\u062c\u0627 \u06a9\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u0645\u061f"


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


def _system_prompt(store: MemoryStore, query: str = "") -> str:
    return Dream(store, EchoBackend())._system_message(store.recall(query))["content"]


class CaptureBackend(EchoBackend):
    """Records the messages the agent sends to the model."""

    def __init__(self):
        self.messages = []

    def chat(self, messages, tools=None):
        if tools is not None:
            self.messages = messages
        return {"content": "پاسخ.", "tool_calls": []}


# --------------------------------------------------------------------------
# The prompt must instruct *using* recalled memories, not writing them
# --------------------------------------------------------------------------


def test_system_prompt_instructs_using_recalled_memories(store):
    prompt = _system_prompt(store)
    # Fragments of the usage instruction, as escapes:
    # خاطره (memory), قطعی (settled/true), هرگز اعلام نکن (never announce),
    # مستقیم (directly), دوباره (again — never ask the user to repeat).
    assert "\u062e\u0627\u0637\u0631\u0647" in prompt
    assert "\u0642\u0637\u0639\u06cc" in prompt
    assert "\u0647\u0631\u06af\u0632 \u0627\u0639\u0644\u0627\u0645 \u0646\u06a9\u0646" in prompt
    assert "\u0645\u0633\u062a\u0642\u06cc\u0645" in prompt
    assert "\u062f\u0648\u0628\u0627\u0631\u0647" in prompt
    # remember_fact stays registered and keeps a single-line mention.
    assert "remember_fact" in prompt


def test_system_prompt_has_no_worked_remember_fact_example(store):
    prompt = _system_prompt(store)
    assert "remember_fact(content=" not in prompt
    assert 'kind="semantic"' not in prompt
    assert "importance=0.9" not in prompt
    # Nothing more than the one-line mention remains.
    assert prompt.count("remember_fact") <= 1


# --------------------------------------------------------------------------
# The memory-block markers are Persian, keeping the prompt single-language
# --------------------------------------------------------------------------


def test_agent_markers_match_the_expected_persian():
    assert _MEMORIES_OPEN == _OPEN
    assert _MEMORIES_CLOSE == _CLOSE


def test_recalled_memory_markers_contain_no_ascii_letters():
    assert not re.search(r"[A-Za-z]", _MEMORIES_OPEN)
    assert not re.search(r"[A-Za-z]", _MEMORIES_CLOSE)


def test_recalled_memory_markers_keep_the_bracketed_shape():
    assert _MEMORIES_OPEN.startswith("[") and _MEMORIES_OPEN.endswith("]")
    assert _MEMORIES_CLOSE.startswith("[") and _MEMORIES_CLOSE.endswith("]")


# --------------------------------------------------------------------------
# Recalled memories must reach the system message
# --------------------------------------------------------------------------


def test_memories_that_answer_the_question_reach_the_system_message(store):
    """The reported fault: asked «where do I work?» with both facts in the
    store, the model ignored its own context. The recalled rows must still be
    placed in the system message — and the block that carries them must not
    itself switch languages."""
    store.remember(_FACT_ALI, kind="semantic", importance=0.9)
    store.remember(_FACT_FINTECH, kind="semantic", importance=0.9)
    capture = CaptureBackend()
    turn = Dream(store, capture).run(_ASK_WORK)

    assert len(turn.memories_used) == 2
    system_message = capture.messages[0]
    assert system_message["role"] == "system"
    system = system_message["content"]
    assert _OPEN in system and _CLOSE in system
    assert "RECALLED MEMORIES" not in system
    section = system.split(_OPEN)[1].split(_CLOSE)[0]
    assert _FACT_ALI in section
    assert _FACT_FINTECH in section


# --------------------------------------------------------------------------
# remember_fact stays registered and fully functional
# --------------------------------------------------------------------------


class RememberFactBackend:
    """Scripted backend: asks to remember one fact, then answers normally."""

    def __init__(self, content: str, kind: str = "semantic", importance: float = 0.9):
        self.content = content
        self.kind = kind
        self.importance = importance
        self.calls = 0

    def chat(self, messages, tools=None):
        del tools
        self.calls += 1
        if messages[-1]["role"] == "tool":
            return {"content": "پاسخ عادی.", "tool_calls": []}
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": f"remember-{self.calls}",
                    "name": "remember_fact",
                    "arguments": {
                        "content": self.content,
                        "kind": self.kind,
                        "importance": self.importance,
                    },
                }
            ],
        }


def test_remember_fact_tool_call_is_persisted_and_queryable(store):
    backend = RememberFactBackend("کاربر علی نام دارد")
    turn = Dream(store, backend).run("اسم من علی است")
    assert turn.memories_created, "the turn must record the created memory"
    assert turn.memories_created[0].content == "کاربر علی نام دارد"
    hits = store.recall("علی")
    assert hits and hits[0].content == "کاربر علی نام دارد"
    assert [m.content for m in store.all()] == ["کاربر علی نام دارد"]


def test_two_turn_fact_survives_into_fresh_instance(store):
    first = Dream(store, RememberFactBackend("کاربر قهوه تلخ دوست دارد"))
    first.run("من قهوه تلخ دوست دارم")

    capture = CaptureBackend()
    second = Dream(store, capture)
    second.run("من چه نوشیدنی دوست دارم؟")

    system = capture.messages[0]["content"]
    assert _OPEN in system
    section = system.split(_OPEN)[1].split(_CLOSE)[0]
    assert "کاربر قهوه تلخ دوست دارد" in section


# --------------------------------------------------------------------------
# The language rule must be unambiguous
# --------------------------------------------------------------------------


def test_system_prompt_language_rule_is_unambiguous_and_names_persian(store):
    prompt = _system_prompt(store)
    assert "فارسی" in prompt
    assert "آخرین پیام" in prompt
    assert "هرگز به زبان سومی تغییر نکن" in prompt


# --------------------------------------------------------------------------
# Backslash commands must dispatch like slash commands
# --------------------------------------------------------------------------


def test_backslash_mems_dispatches_identically_to_slash_mems(store):
    store.remember("کاربر روی پروژه‌ای به نام Dream کار می‌کند")
    dream = Dream(store, EchoBackend())
    slash_output = []
    backslash_output = []
    assert cli.dispatch_command("/mems", dream, slash_output.append) is True
    assert cli.dispatch_command("\\mems", dream, backslash_output.append) is True
    assert slash_output == backslash_output
    assert "Dream" in slash_output[0]


def test_backslash_exit_ends_the_session(store):
    assert cli.dispatch_command("\\exit", Dream(store, EchoBackend())) is False


def test_unknown_command_suggests_close_match_instead_of_reaching_model(store):
    dream = Dream(store, EchoBackend())
    output = []
    assert cli.dispatch_command("\\mms", dream, output.append) is True
    assert output == [
        "Unknown command: /mms. Did you mean /mems? Type /help to see available commands."
    ]
    assert dream.history == [], "an unknown command must never reach the model"


def test_unknown_command_without_close_match_still_stays_in_cli(store):
    dream = Dream(store, EchoBackend())
    output = []
    assert cli.dispatch_command("/nonsense", dream, output.append) is True
    assert output == ["Unknown command: /nonsense. Type /help to see available commands."]
    assert dream.history == []
