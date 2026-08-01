"""Tests for the separate fact extraction pass, normalization, and CLI observability."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

import cli
from dream.agent import Dream, Turn
from dream.extraction import (
    STATUS_DISABLED,
    STATUS_ERROR,
    STATUS_FACTS_FOUND,
    STATUS_NO_FACTS,
    STATUS_TOO_SHORT,
    STATUS_UNPARSEABLE,
    ExtractionResult,
    extract_facts,
)
from dream.memory import MemoryStore
from dream.normalization import normalize_importance, normalize_kind
from tools import memory_probe


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


class ExtractionBackend:
    """Mock backend that returns a fixed response for extraction calls."""

    def __init__(self, response: Any):
        self.response = response
        self.calls: list[list[dict[str, Any]]] = []

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        self.calls.append(messages)
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, dict):
            return self.response
        return {"content": str(self.response), "tool_calls": []}


class TurnBackend:
    """Mock backend for full Dream turns with separate conversation and extraction."""

    def __init__(
        self, conv_reply: str, ext_response: str | dict[str, Any] | Exception
    ) -> None:
        self.conv_reply = conv_reply
        self.ext_response = ext_response
        self.conv_calls = 0
        self.ext_calls = 0
        self.ext_messages: list[list[dict[str, Any]]] = []

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        if tools is not None:
            self.conv_calls += 1
            return {"content": self.conv_reply, "tool_calls": []}
        self.ext_calls += 1
        self.ext_messages.append(messages)
        if isinstance(self.ext_response, Exception):
            raise self.ext_response
        if isinstance(self.ext_response, dict):
            return self.ext_response
        return {"content": str(self.ext_response), "tool_calls": []}


class ToolCallingTurnBackend:
    """Emits tool calls in conversation, responds in prose, then handles extraction."""

    def __init__(self, ext_response: str) -> None:
        self.ext_response = ext_response
        self.conv_calls = 0
        self.ext_calls = 0

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        if tools is not None:
            self.conv_calls += 1
            if self.conv_calls == 1:
                return {
                    "content": None,
                    "tool_calls": [
                        {"id": "call1", "name": "get_datetime", "arguments": "{}"}
                    ],
                }
            if self.conv_calls == 2:
                return {
                    "content": None,
                    "tool_calls": [
                        {"id": "call2", "name": "get_datetime", "arguments": "{}"}
                    ],
                }
            return {"content": "Conversation reply after tool calls.", "tool_calls": []}
        self.ext_calls += 1
        return {"content": self.ext_response, "tool_calls": []}


# --------------------------------------------------------------------------
# Defensive JSON parsing
# --------------------------------------------------------------------------


def test_clean_json_array():
    payload = '[{"content": "کاربر علی نام دارد", "kind": "semantic", "importance": 0.9}]'
    backend = ExtractionBackend(payload)
    result = extract_facts(backend, "من علی هستم و روی استارتاپ کار می‌کنم")
    assert result.status == STATUS_FACTS_FOUND
    assert len(result.facts) == 1
    assert result.facts[0].content == "کاربر علی نام دارد"
    assert result.facts[0].kind == "semantic"
    assert result.facts[0].importance == pytest.approx(0.9)


def test_json_wrapped_in_prose():
    payload = (
        'Sure! Here is the output: [{"content": "کاربر پایتون کار می‌کند", '
        '"kind": "semantic"}] done.'
    )
    backend = ExtractionBackend(payload)
    result = extract_facts(backend, "من همیشه با پایتون کار می‌کنم")
    assert result.status == STATUS_FACTS_FOUND
    assert len(result.facts) == 1
    assert result.facts[0].content == "کاربر پایتون کار می‌کند"


def test_json_wrapped_in_fenced_block():
    payload = 'note [important]: ```json\n[{"content": "کاربر روی فین‌تک کار می‌کند"}]\n```'
    backend = ExtractionBackend(payload)
    result = extract_facts(backend, "استارتاپ من در حوزه فین‌تک است")
    assert result.status == STATUS_FACTS_FOUND
    assert len(result.facts) == 1
    assert result.facts[0].content == "کاربر روی فین‌تک کار می‌کند"


def test_bare_object_instead_of_array():
    payload = '{"content": "کاربر فردا جلسه دارد", "kind": "episodic", "importance": 0.7}'
    backend = ExtractionBackend(payload)
    result = extract_facts(backend, "فردا با تیم طراحی جلسه دارم")
    assert result.status == STATUS_FACTS_FOUND
    assert len(result.facts) == 1
    assert result.facts[0].content == "کاربر فردا جلسه دارد"
    assert result.facts[0].kind == "episodic"


def test_json_string_containing_brace_or_bracket_character():
    payload = (
        '[{"content": "کاربر تابع foo(x=[1]) { return {} } را دوست دارد", '
        '"kind": "semantic", "importance": 0.8}]'
    )
    backend = ExtractionBackend(payload)
    result = extract_facts(
        backend, "من تابع foo(x=[1]) { return {} } را برای کدنویسی دوست دارم"
    )
    assert result.status == STATUS_FACTS_FOUND
    assert len(result.facts) == 1
    assert "foo(x=[1]) { return {} }" in result.facts[0].content


def test_unparseable_text():
    payload = "This is not JSON at all and cannot be decoded."
    backend = ExtractionBackend(payload)
    result = extract_facts(backend, "پیام کاربر با متن بلند برای استخراج")
    assert result.status == STATUS_UNPARSEABLE
    assert result.facts == []
    assert result.raw_text == payload


def test_backend_raises_exception():
    backend = ExtractionBackend(RuntimeError("backend connection lost"))
    result = extract_facts(backend, "پیام کاربر با متن بلند برای استخراج")
    assert result.status == STATUS_ERROR
    assert result.facts == []
    assert "backend connection lost" in result.raw_text


def test_small_talk_producing_empty_array():
    payload = "[]"
    backend = ExtractionBackend(payload)
    result = extract_facts(backend, "سلام چطور هستید امروز؟")
    assert result.status == STATUS_NO_FACTS
    assert result.facts == []


# --------------------------------------------------------------------------
# Normalization flow
# --------------------------------------------------------------------------


def test_kind_and_importance_shared_normalization():
    payload = '[{"content": "کاربر", "kind": " EPISODIC ", "importance": "0.85"}]'
    backend = ExtractionBackend(payload)
    result = extract_facts(backend, "یک پیام درباره رویدادهای کاربر")
    assert result.facts[0].kind == "episodic"
    assert result.facts[0].importance == pytest.approx(0.85)


def test_persian_synonyms_in_normalization():
    assert normalize_kind("رویدادی") == "episodic"
    assert normalize_kind("رویه ای") == "procedural"
    assert normalize_importance("۰.۸") == pytest.approx(0.8)


# --------------------------------------------------------------------------
# Guards against cost and failure
# --------------------------------------------------------------------------


def test_short_messages_skip_model_call():
    backend = ExtractionBackend("[]")
    result = extract_facts(backend, "سلام")
    assert result.status == STATUS_TOO_SHORT
    assert len(backend.calls) == 0


def test_command_like_messages_skip_model_call():
    backend = ExtractionBackend("[]")
    result = extract_facts(backend, "/mems")
    assert result.status == STATUS_TOO_SHORT
    assert len(backend.calls) == 0


@pytest.mark.parametrize("val", ["off", "0", "false", "no"])
def test_environment_variable_disables_pass(val):
    backend = ExtractionBackend("[]")
    result = extract_facts(
        backend,
        "من علی هستم و روی استارتاپ فین‌تک کار می‌کنم",
        env={"DREAM_EXTRACTION": val},
    )
    assert result.status == STATUS_DISABLED
    assert len(backend.calls) == 0


# --------------------------------------------------------------------------
# Agent wiring and reply isolation
# --------------------------------------------------------------------------


def test_agent_stores_extracted_facts_and_reports_them(store):
    payload = '[{"content": "کاربر علی نام دارد", "kind": "semantic", "importance": 0.9}]'
    backend = TurnBackend("سلام علی", payload)
    turn = Dream(store, backend).run("من علی هستم و روی استارتاپ کار می‌کنم")
    assert len(turn.memories_created) == 1
    assert turn.memories_created[0].content == "کاربر علی نام دارد"
    assert turn.memories_created[0].source == "extraction"
    assert turn.extraction.status == STATUS_FACTS_FOUND

    lines: list[str] = []
    cli.report_turn_activity(turn, lines.append)
    assert any("[extraction] facts found: 1 fact" in line for line in lines)
    assert any("[memory] stored 1 fact" in line for line in lines)


def test_agent_still_replies_when_extraction_fails(store):
    backend = TurnBackend("سلام کاربر", RuntimeError("extraction down"))
    turn = Dream(store, backend).run("من علی هستم و روی استارتاپ کار می‌کنم")
    assert turn.reply == "سلام کاربر"
    assert turn.memories_created == []
    assert turn.extraction.status == STATUS_ERROR


def test_extraction_runs_exactly_once_per_turn(store):
    payload = '[{"content": "کاربر برنامه را تست می‌کند", "kind": "semantic"}]'
    backend = ToolCallingTurnBackend(payload)
    turn = Dream(store, backend).run("بگو ساعت چند است و تاریخ چیست")
    assert backend.conv_calls == 3
    assert backend.ext_calls == 1
    assert turn.extraction is not None
    assert turn.extraction.status == STATUS_FACTS_FOUND


def test_assistant_reply_only_phrase_never_stored(store):
    """Prove a string present only in an assistant reply is never sent or stored."""
    user_msg = "من روی استارتاپ فین‌تک کار می‌کنم"
    assistant_reply = "شما روی استارتاپ فناوری مالی (money technology) کار می‌کنید."
    backend = TurnBackend(
        assistant_reply,
        '[{"content": "کاربر روی استارتاپ فین‌تک کار می‌کند", "kind": "semantic"}]',
    )
    turn = Dream(store, backend).run(user_msg)

    ext_messages = backend.ext_messages[0]
    all_text = " ".join(str(m.get("content", "")) for m in ext_messages)
    assert "money technology" not in all_text
    assert "فناوری مالی" not in all_text
    assert "money technology" not in turn.reply or "فناوری مالی" in turn.reply
    assert len(turn.memories_created) == 1
    assert "money technology" not in turn.memories_created[0].content


# --------------------------------------------------------------------------
# CLI observability and quiet flag
# --------------------------------------------------------------------------


def test_cli_extraction_line_appears_on_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input",
        lambda _="": (_ for _ in ()).throw(EOFError),
    )
    turn = Turn(
        reply="hello",
        tool_calls=[],
        memories_used=[],
        memories_created=[],
        elapsed_seconds=0.1,
        extraction=ExtractionResult(facts=[], status=STATUS_NO_FACTS),
    )
    cli.report_turn_activity(turn)
    err = capsys.readouterr().err
    assert "[extraction] no durable facts" in err


def test_cli_quiet_flag_suppresses_extraction_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input",
        lambda _="": (_ for _ in ()).throw(EOFError),
    )
    db_path = str(tmp_path / "quiet.db")
    assert cli.main(["--quiet", "--db", db_path]) == 0
    err = capsys.readouterr().err
    assert "[extraction]" not in err


# --------------------------------------------------------------------------
# Probe verdicts for extraction fail modes
# --------------------------------------------------------------------------


def test_probe_reports_absence_of_tool_call_as_information(store):
    payload = '[{"content": "کاربر علی است", "kind": "semantic"}]'
    backend = TurnBackend("سلام", payload)
    report = memory_probe.run_probe(backend)
    rendered = report.render()
    assert "tool calls: none (no tool call emitted)" in rendered
    assert report.extraction_ran is True
    assert report.facts_stored == 1
    assert "OK: memory stored successfully" in report.verdict
    assert report.ok is True


def test_probe_verdict_extraction_returned_no_facts():
    backend = TurnBackend("سلام", "[]")
    report = memory_probe.run_probe(backend)
    assert "extraction returned no facts" in report.verdict
    assert report.ok is False


def test_probe_verdict_extraction_could_not_be_parsed():
    backend = TurnBackend("سلام", "Not JSON output")
    report = memory_probe.run_probe(backend)
    assert "extraction could not be parsed" in report.verdict
    assert report.ok is False


def test_probe_verdict_facts_extracted_but_none_stored(store, monkeypatch):
    payload = '[{"content": "کاربر علی است", "kind": "semantic"}]'
    backend = TurnBackend("سلام", payload)

    def _fail_remember(*args, **kwargs):
        raise ValueError("store rejected")

    monkeypatch.setattr(MemoryStore, "remember", _fail_remember)
    report = memory_probe.run_probe(backend)
    assert "facts extracted but none stored" in report.verdict
    assert report.ok is False


# --------------------------------------------------------------------------
# Store failures: only the unusable-fact case may stay quiet
#
# The store write used to sit under ``except (ValueError, Exception)``,
# which swallowed every error — with a locked database the turn reported
# «facts found: 1» while nothing was stored and no trace existed anywhere.
# --------------------------------------------------------------------------


def test_store_operational_error_is_visible_not_swallowed(store, monkeypatch):
    payload = '[{"content": "کاربر علی نام دارد", "kind": "semantic", "importance": 0.9}]'
    backend = TurnBackend("سلام علی", payload)

    def _locked_remember(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(MemoryStore, "remember", _locked_remember)
    turn = Dream(store, backend).run("من علی هستم و روی استارتاپ کار می‌کند")

    assert turn.reply == "سلام علی", "the conversation itself must still complete"
    assert turn.extraction.status == STATUS_FACTS_FOUND
    assert turn.memories_created == []
    assert turn.memory_errors == ["OperationalError: database is locked"]

    lines: list[str] = []
    cli.report_turn_activity(turn, lines.append)
    assert any("[extraction] facts found: 1 fact" in line for line in lines)
    assert any("store failed" in line and "OperationalError" in line for line in lines)
    assert any("database is locked" in line for line in lines)


def test_invalid_fact_value_error_is_skipped_quietly(store, monkeypatch):
    """The skip path exists for one case only: a fact the store rejects."""
    payload = '[{"content": "کاربر علی نام دارد", "kind": "semantic", "importance": 0.9}]'
    backend = TurnBackend("سلام علی", payload)

    def _rejecting_remember(*args, **kwargs):
        raise ValueError("content must not be empty")

    monkeypatch.setattr(MemoryStore, "remember", _rejecting_remember)
    turn = Dream(store, backend).run("من علی هستم و روی استارتاپ کار می‌کند")

    assert turn.reply == "سلام علی"
    assert turn.memories_created == []
    assert turn.memory_errors == [], "the expected rejection stays off the error list"
