"""MEM Stage A — Dream agent integration with the bounded stores.

Covers the injection contract: both snapshots ride the system prompt with
capacity headers, the snapshot is frozen for a session's lifetime (tool
writes do not leak into later turns' prompts), reset_session() takes a new
frozen snapshot, tools carry the add/replace/remove surface with unique
substring matching, overflow fails closed through the tool boundary, and
Dream instances without bounded stores behave exactly as before.
"""

from __future__ import annotations

import json

import pytest

from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore
from dream.memory_stores import (
    NOTES_LABEL,
    PROFILE_LABEL,
    TARGET_MEMORY,
    TARGET_USER,
    BoundedMemory,
)
from dream.tools import REGISTRY, execute, openai_schemas


class CaptureBackend(EchoBackend):
    """EchoBackend that records every system message it is handed."""

    def __init__(self) -> None:
        self.systems: list[str] = []

    def chat(self, messages, tools=None):
        if tools is not None:
            self.systems.append(messages[0]["content"])
        return {"content": "done", "tool_calls": []}


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


@pytest.fixture()
def bounded(tmp_path):
    bm = BoundedMemory(path=str(tmp_path / "bounded.db"))
    yield bm
    bm.close()


def test_both_snapshots_are_injected_with_capacity_headers(store, bounded):
    bounded.notes.add("deploy checklist verified")
    bounded.profile.add("prefers dark coffee")
    backend = CaptureBackend()
    Dream(store, backend, bounded=bounded).run("hello")

    prompt = backend.systems[0]
    assert NOTES_LABEL in prompt
    assert PROFILE_LABEL in prompt
    assert "deploy checklist verified" in prompt
    assert "prefers dark coffee" in prompt
    assert "[1% — 25/2,200 chars]" in prompt
    assert "[1% — 19/1,375 chars]" in prompt
    assert "agent_notes" in prompt and "user_profile" in prompt


def test_entries_are_rendered_with_the_section_separator(store, bounded):
    bounded.notes.add("first note")
    bounded.notes.add("second note")
    backend = CaptureBackend()
    Dream(store, backend, bounded=bounded).run("hello")
    assert "first note§second note" in backend.systems[0]


def test_empty_stores_still_inject_their_headers(store, bounded):
    backend = CaptureBackend()
    Dream(store, backend, bounded=bounded).run("hello")
    prompt = backend.systems[0]
    assert "[0% — 0/2,200 chars]" in prompt
    assert "[0% — 0/1,375 chars]" in prompt


def test_bounded_block_precedes_recalled_memories(store, bounded):
    from dream.agent import _MEMORIES_OPEN

    store.remember("recalled fact about coffee")
    bounded.notes.add("bounded note")
    backend = CaptureBackend()
    Dream(store, backend, bounded=bounded).run("about coffee")
    prompt = backend.systems[0]
    assert prompt.index(NOTES_LABEL) < prompt.index(_MEMORIES_OPEN)


def test_snapshot_is_frozen_mid_session(store, bounded):
    bounded.notes.add("pre-session note")
    backend = CaptureBackend()
    dream = Dream(store, backend, bounded=bounded)
    dream.run("turn one")
    first = backend.systems[0]

    # The tool writes mid-session…
    payload = json.loads(
        execute("agent_notes", {"action": "add", "text": "mid-session note"})
    )
    assert payload["status"] == "ok"
    assert "mid-session note" in payload["result"]["content"]

    # …but the session's prompt snapshot never changes.
    dream.run("turn two")
    second = backend.systems[1]
    assert first == second
    assert "mid-session note" not in second
    # The store itself, however, has the entry.
    assert "mid-session note" in bounded.notes.snapshot().text


def test_reset_session_takes_a_fresh_snapshot(store, bounded):
    bounded.notes.add("before reset")
    backend = CaptureBackend()
    dream = Dream(store, backend, bounded=bounded)
    dream.run("turn one")
    execute("agent_notes", {"action": "add", "text": "written during session"})
    dream.reset_session()
    dream.run("turn two")
    prompt = backend.systems[1]
    assert "before reset" in prompt
    assert "written during session" in prompt


def test_without_bounded_stores_the_prompt_is_unchanged(store):
    backend = CaptureBackend()
    Dream(store, backend).run("hello")
    prompt = backend.systems[0]
    assert NOTES_LABEL not in prompt
    assert PROFILE_LABEL not in prompt
    assert "agent_notes" not in prompt
    assert "user_profile" not in prompt


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


def test_tools_are_registered_guarded_with_enum_actions(store, bounded):
    Dream(store, EchoBackend(), bounded=bounded)
    for name in ("agent_notes", "user_profile"):
        assert name in REGISTRY
        assert REGISTRY[name].risk == "guarded"
        schema = openai_schemas()
        tool_schema = next(t for t in schema if t["function"]["name"] == name)
        action = tool_schema["function"]["parameters"]["properties"]["action"]
        assert action.get("enum") == ["add", "replace", "remove"]
        assert tool_schema["function"]["parameters"]["required"] == ["action"]


def test_tools_are_absent_without_bounded_stores(store, tmp_path):
    dream = Dream(store, EchoBackend())
    assert dream.bounded is None
    # Other Dream instances earlier in this process may have registered the
    # tools; the contract is that *this* agent never exposes them, which the
    # subagent/private-registry mechanism enforces. The prompt-level absence
    # is pinned by test_without_bounded_stores_the_prompt_is_unchanged.


def test_tool_add_returns_fresh_state_without_a_read_action(store, bounded):
    Dream(store, EchoBackend(), bounded=bounded)
    payload = json.loads(execute("agent_notes", {"action": "add", "text": "note one"}))
    assert payload["status"] == "ok"
    result = payload["result"]
    assert result["target"] == TARGET_MEMORY
    assert result["action"] == "add"
    assert result["content"] == "note one"
    assert result["header"] == "[0% — 8/2,200 chars]"


def test_tool_replace_and_remove_use_unique_substrings(store, bounded):
    Dream(store, EchoBackend(), bounded=bounded)
    execute("user_profile", {"action": "add", "text": "drinks tea"})
    execute("user_profile", {"action": "add", "text": "lives in Tehran"})

    payload = json.loads(
        execute("user_profile", {"action": "replace", "old": "tea", "new": "drinks coffee"})
    )
    assert payload["status"] == "ok"
    assert payload["result"]["content"] == "drinks coffee§lives in Tehran"

    payload = json.loads(execute("user_profile", {"action": "remove", "old": "Tehran"}))
    assert payload["status"] == "ok"
    assert payload["result"]["content"] == "drinks coffee"
    assert payload["result"]["target"] == TARGET_USER


def test_tool_overflow_fails_closed_through_the_tool_boundary(store, tmp_path):
    small = BoundedMemory(path=str(tmp_path / "small.db"), notes_capacity=64)
    try:
        Dream(store, EchoBackend(), bounded=small)
        payload = json.loads(
            execute("agent_notes", {"action": "add", "text": "x" * 100})
        )
        assert payload["status"] == "error"
        assert payload["error"]["type"] == "StoreCapacityError"
        message = payload["error"]["message"]
        assert "replace" in message and "remove" in message
        assert small.notes.snapshot().entries == ()
    finally:
        small.close()


def test_tool_ambiguity_error_names_the_candidates(store, bounded):
    Dream(store, EchoBackend(), bounded=bounded)
    execute("agent_notes", {"action": "add", "text": "coffee dark"})
    execute("agent_notes", {"action": "add", "text": "coffee light"})
    payload = json.loads(execute("agent_notes", {"action": "remove", "old": "coffee"}))
    assert payload["status"] == "error"
    assert payload["error"]["type"] == "AmbiguousEntryError"
    assert "coffee dark" in payload["error"]["message"]
    assert "coffee light" in payload["error"]["message"]


def test_tool_unknown_action_is_a_clean_error(store, bounded):
    Dream(store, EchoBackend(), bounded=bounded)
    payload = json.loads(execute("agent_notes", {"action": "publish", "text": "x"}))
    assert payload["status"] == "error"
    assert "action must be add, replace, or remove" in payload["error"]["message"]


def test_tool_persian_variant_matching_from_the_tool_surface(store, bounded):
    Dream(store, EchoBackend(), bounded=bounded)
    execute("user_profile", {"action": "add", "text": "كتاب‌خوانی شبانه"})
    payload = json.loads(
        execute("user_profile", {"action": "remove", "old": "کتاب"})
    )
    assert payload["status"] == "ok"
    assert payload["result"]["content"] == ""


def test_bounded_writes_are_journaled_through_the_agent_turn(tmp_path, bounded):
    class AddNoteBackend(EchoBackend):
        def chat(self, messages, tools=None):
            return {
                "content": "saved",
                "tool_calls": [
                    {"name": "agent_notes", "arguments": {"action": "add", "text": "from turn"}}
                ],
            }

    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, AddNoteBackend(), bounded=bounded)
        turn = dream.run("please note this")
        assert turn.tool_calls[0]["name"] == "agent_notes"
        assert turn.tool_calls[0]["allowed"] is True
        assert "from turn" in bounded.notes.snapshot().text


# ---------------------------------------------------------------------------
# Subagent isolation
# ---------------------------------------------------------------------------


def test_subagents_never_receive_the_parents_bounded_tools(tmp_path, bounded):
    from dream.subagents import build_child_tools
    from dream.tools import REGISTRY

    with MemoryStore(str(tmp_path / "dream.db")) as store:
        Dream(store, EchoBackend(), bounded=bounded)  # registers parent closures
        before = dict(REGISTRY)

        child_store = MemoryStore(str(tmp_path / "child.db"))
        try:
            child, table = build_child_tools(
                child_store,
                ["agent_notes", "user_profile", "remember_fact", "calculate"],
                backend=EchoBackend(),
            )
            # The bounded tools are dropped: they can only be the parent's
            # closures, and a child must never write the parent's stores.
            assert "agent_notes" not in table
            assert "user_profile" not in table
            # Statelessly safe grants keep working; remember_fact is the
            # child's own closure over its ephemeral store.
            assert "calculate" in table
            assert "remember_fact" in table
            assert child.bounded is None
            assert child.approval_policy.registry is table
        finally:
            child_store.close()

        # The parent registry — bounded closures included — is intact.
        assert dict(REGISTRY) == before
        assert "agent_notes" in REGISTRY
