"""Tests for the memory policy, the language rule, and backslash commands.

These cover the three reported defects: the model was never told to call
``remember_fact``, the language rule was soft enough to allow drift, and
backslash commands fell through to the model. All tests run offline against
``EchoBackend`` or scripted mocks — no network, no API keys.
"""

from __future__ import annotations

import pytest

import cli
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


def _system_prompt(store: MemoryStore, query: str = "") -> str:
    return Dream(store, EchoBackend())._system_message(store.recall(query))["content"]


# --------------------------------------------------------------------------
# DEFECT 1: the model must be told when to store memories
# --------------------------------------------------------------------------


def test_system_prompt_contains_memory_policy_and_names_remember_fact(store):
    prompt = _system_prompt(store)
    assert "remember_fact" in prompt
    assert "سیاست حافظه" in prompt
    # Every part of the policy must be present, not just the tool name.
    assert "واقعیت ماندگار" in prompt
    assert "سلام‌ها" in prompt
    assert "semantic" in prompt and "episodic" in prompt and "procedural" in prompt
    assert "importance" in prompt
    assert "بی‌صدا" in prompt


def test_system_prompt_contains_worked_remember_fact_example(store):
    prompt = _system_prompt(store)
    assert "مثال" in prompt
    assert "remember_fact(content=" in prompt
    assert "kind=\"semantic\"" in prompt
    assert "importance=0.9" in prompt


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

    class CaptureBackend(EchoBackend):
        def __init__(self):
            self.messages = []

        def chat(self, messages, tools=None):
            if tools is not None:
                self.messages = messages
            return {"content": "پاسخ.", "tool_calls": []}

    capture = CaptureBackend()
    second = Dream(store, capture)
    second.run("من چه نوشیدنی دوست دارم؟")

    system = capture.messages[0]["content"]
    assert "RECALLED MEMORIES" in system
    section = system.split("[RECALLED MEMORIES — PRIVATE CONTEXT]")[1].split("[END MEMORIES]")[0]
    assert "کاربر قهوه تلخ دوست دارد" in section


# --------------------------------------------------------------------------
# DEFECT 2: the language rule must be unambiguous
# --------------------------------------------------------------------------


def test_system_prompt_language_rule_is_unambiguous_and_names_persian(store):
    prompt = _system_prompt(store)
    assert "فارسی" in prompt
    assert "آخرین پیام" in prompt
    assert "هرگز به زبان سومی تغییر نکن" in prompt


# --------------------------------------------------------------------------
# DEFECT 3: backslash commands must dispatch like slash commands
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
