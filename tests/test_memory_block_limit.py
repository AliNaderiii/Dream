"""Tests for the recalled-memory prompt budget and its CLI visibility."""

from __future__ import annotations

import time

import pytest

import cli
from dream.agent import (
    _MEMORIES_CLOSE,
    _MEMORIES_OPEN,
    DEFAULT_MEMORY_BLOCK_CHAR_LIMIT,
    Dream,
    EchoBackend,
)
from dream.memory import Memory, MemoryStore


@pytest.fixture()
def store(tmp_path):
    memory_store = MemoryStore(str(tmp_path / "dream.db"))
    yield memory_store
    memory_store.close()


def _memory(memory_id: int, content: str, score: float) -> Memory:
    return Memory(
        id=memory_id,
        kind="episodic",
        content=content,
        norm=content,
        created_at=time.time(),
        score=score,
    )


def _line(memory: Memory) -> str:
    return f"- [today] {memory.content}"


def _section(prompt: str) -> str:
    return prompt.split(_MEMORIES_OPEN, 1)[1].split(_MEMORIES_CLOSE, 1)[0]


def _feeding_input(lines):
    iterator = iter(lines)

    def read(_prompt=""):
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return read


def test_block_under_the_ceiling_is_unchanged(store):
    memory = _memory(1, "short recalled fact", 0.9)

    prompt = Dream(store, EchoBackend())._system_message([memory])["content"]

    assert len(_line(memory)) < DEFAULT_MEMORY_BLOCK_CHAR_LIMIT
    assert _section(prompt) == f"\n{_line(memory)}\n"


def test_block_over_the_ceiling_drops_whole_lines(store, monkeypatch):
    first = _memory(1, "first whole line", 0.9)
    dropped = _memory(2, "this line must never be partially injected", 0.8)
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", str(len(_line(first))))

    prompt = Dream(store, EchoBackend())._system_message([first, dropped])["content"]

    assert _section(prompt) == f"\n{_line(first)}\n"
    assert dropped.content not in prompt


def test_memory_block_keeps_the_highest_scoring_memories(store, monkeypatch):
    low = _memory(1, "low score memory", 0.1)
    middle = _memory(2, "middle score memory", 0.8)
    high = _memory(3, "high score memory", 0.9)
    limit = len(_line(high)) + 1 + len(_line(middle))
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", str(limit))

    block, injected = Dream(store, EchoBackend())._memory_block([low, middle, high])

    assert [memory.id for memory in injected] == [high.id, middle.id]
    assert _section(block) == f"\n{_line(high)}\n{_line(middle)}\n"
    assert low.content not in block


def test_memory_block_keeps_both_markers_when_every_memory_is_dropped(store, monkeypatch):
    memory = _memory(1, "too long for a one character budget", 0.9)
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", "1")

    prompt = Dream(store, EchoBackend())._system_message([memory])["content"]

    assert prompt.count(_MEMORIES_OPEN) == 1
    assert prompt.count(_MEMORIES_CLOSE) == 1
    assert _section(prompt) == "\n"
    assert memory.content not in prompt


def test_memory_block_environment_override_controls_the_budget(store, monkeypatch):
    memory = _memory(1, "exactly one permitted memory", 0.9)
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", str(len(_line(memory))))

    dream = Dream(store, EchoBackend())
    _block, injected = dream._memory_block([memory])

    assert dream.memory_block_char_limit == len(_line(memory))
    assert injected == [memory]


@pytest.mark.parametrize("raw", ["not-a-number", "0", "-1", "100001", "1.5", "NaN"])
def test_invalid_memory_block_environment_falls_back_without_raising(store, monkeypatch, raw):
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", raw)

    dream = Dream(store, EchoBackend())

    assert dream.memory_block_char_limit == DEFAULT_MEMORY_BLOCK_CHAR_LIMIT


@pytest.mark.parametrize(("quiet", "visible"), [(False, True), (True, False)])
def test_cli_reports_memory_block_drops_unless_quiet(tmp_path, monkeypatch, capsys, quiet, visible):
    path = str(tmp_path / "cli.db")
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", "1")
    with MemoryStore(path) as seeded:
        seeded.remember("coffee preference", kind="episodic")

    monkeypatch.setattr("builtins.input", _feeding_input(["coffee"]))
    arguments = ["--backend", "echo", "--db", path]
    if quiet:
        arguments.insert(0, "--quiet")

    assert cli.main(arguments) == 0
    expected = "[memory] recalled 1, injected 0 (block limit)"
    assert (expected in capsys.readouterr().err.splitlines()) is visible


def test_single_oversized_memory_keeps_complete_markers_and_returns(store, monkeypatch):
    class CaptureBackend:
        def __init__(self):
            self.calls = 0
            self.system_prompt = ""

        def chat(self, messages, tools=None):
            self.calls += 1
            if tools is not None:
                self.system_prompt = messages[0]["content"]
                return {"content": "done", "tool_calls": []}
            return {"content": "[]", "tool_calls": []}

    oversized = "coffee " + "very long detail " * 20
    store.remember(oversized, kind="episodic")
    monkeypatch.setenv("DREAM_MEMORY_BLOCK_CHAR_LIMIT", "1")
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    backend = CaptureBackend()

    turn = Dream(store, backend).run("What coffee detail do you remember?")

    assert len(turn.memories_used) == 1
    assert turn.memories_injected == []
    assert backend.calls == 1
    assert backend.system_prompt.endswith(f"{_MEMORIES_OPEN}\n{_MEMORIES_CLOSE}")
    assert oversized not in backend.system_prompt
