"""Tests for tool-activity visibility, explicit tool failures, and tolerant
memory writes.

The reported defect: the model replied «ذخیره شد» (stored) while ``/mems``
showed nothing. Two invisible causes produce that identical symptom — the
model never emitted a tool call, or the call failed and the failure was
narrated as success. These tests pin the three fixes plus the committed
probe: every call is surfaced on stderr, failures are marked so they cannot
be misread as results, ``remember_fact`` normalises sloppy kinds and
importances instead of dropping the memory, and ``tools/memory_probe.py``
names the failure mode without a network or API key.
"""

from __future__ import annotations

import json

import pytest

import cli
from dream import tools
from dream.agent import ApprovalPolicy, Dream, EchoBackend
from dream.memory import MemoryStore
from tools import memory_probe


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


@pytest.fixture()
def dream(store):
    """A Dream bound to the test store, so remember_fact targets that store."""
    return Dream(store, EchoBackend())


def _feeding_input(lines):
    """Replacement for builtins.input that ends input with EOFError."""
    iterator = iter(lines)

    def _input(prompt=""):
        del prompt
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return _input


class ScriptedBackend:
    """Backend that emits a fixed set of tool calls once, then answers prose."""

    def __init__(self, calls):
        self.calls = list(calls)

    def chat(self, messages, tools=None):
        del tools
        if messages[-1]["role"] == "tool":
            return {"content": "پاسخ عادی.", "tool_calls": []}
        return {
            "content": None,
            "tool_calls": [
                {"id": f"scripted-{index}", "name": name, "arguments": arguments}
                for index, (name, arguments) in enumerate(self.calls)
            ],
        }


def _remember(arguments):
    payload = json.loads(tools.execute("remember_fact", arguments))
    assert payload["status"] == "ok", payload
    return payload["result"]


# --------------------------------------------------------------------------
# [tool] / [memory] lines: what the user sees after each turn
# --------------------------------------------------------------------------


def test_successful_tool_call_produces_tool_line_naming_the_tool(store):
    turn = Dream(store, EchoBackend()).run("What time is it?")
    lines = []
    cli.report_turn_activity(turn, lines.append)
    tool_lines = [line for line in lines if line.startswith("[tool]")]
    assert len(tool_lines) == 1
    assert "get_datetime" in tool_lines[0]
    assert "-> ok" in tool_lines[0]


def test_failed_tool_call_produces_line_containing_error(store):
    backend = ScriptedBackend([("calculate", {"expression": "not arithmetic"})])
    turn = Dream(store, backend).run("calculate something")
    lines = []
    cli.report_turn_activity(turn, lines.append)
    tool_lines = [line for line in lines if line.startswith("[tool]")]
    assert len(tool_lines) == 1
    assert "error" in tool_lines[0]
    assert "calculate" in tool_lines[0]


def test_blocked_dangerous_tool_produces_line_containing_blocked(store):
    backend = ScriptedBackend([("run_shell", {"command": "rm -rf /"})])
    turn = Dream(store, backend, ApprovalPolicy()).run("run a command")
    assert turn.tool_calls[0]["allowed"] is False
    lines = []
    cli.report_turn_activity(turn, lines.append)
    tool_lines = [line for line in lines if line.startswith("[tool]")]
    assert len(tool_lines) == 1
    assert "blocked" in tool_lines[0]
    assert "run_shell" in tool_lines[0]


def test_long_arguments_are_truncated():
    line = cli.format_tool_line(
        "remember_fact", {"content": "x" * 500}, '{"status": "ok", "result": {}}'
    )
    assert len(line) < 200
    assert "..." in line


def test_turn_without_tool_calls_stays_silent(store):
    turn = Dream(store, EchoBackend()).run("سلام")
    lines = []
    cli.report_turn_activity(turn, lines.append)
    assert lines == []


def test_memory_creation_produces_memory_line_with_count(store):
    backend = ScriptedBackend(
        [
            ("remember_fact", {"content": "کاربر علی نام دارد"}),
            ("remember_fact", {"content": "کاربر روی یک استارتاپ فین‌تک کار می‌کند"}),
        ]
    )
    turn = Dream(store, backend).run("اسم من علی است")
    assert len(turn.memories_created) == 2
    lines = []
    cli.report_turn_activity(turn, lines.append)
    assert "[memory] stored 2 facts" in lines


def test_single_memory_uses_singular(store):
    backend = ScriptedBackend([("remember_fact", {"content": "کاربر علی نام دارد"})])
    turn = Dream(store, backend).run("اسم من علی است")
    lines = []
    cli.report_turn_activity(turn, lines.append)
    assert "[memory] stored 1 fact" in lines
    assert "stored 1 facts" not in lines


# --------------------------------------------------------------------------
# --quiet: visibility defaults on, opt-out per invocation
# --------------------------------------------------------------------------


def test_quiet_flag_defaults_to_showing_tool_lines():
    assert cli.build_parser().parse_args([]).quiet is False


def test_tool_lines_appear_on_stderr_not_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _feeding_input(["What time is it?"]))
    assert cli.main(["--db", str(tmp_path / "show.db")]) == 0
    captured = capsys.readouterr()
    assert any(line.startswith("[tool] get_datetime(") for line in captured.err.splitlines())
    assert "[tool]" not in captured.out, "piped stdout must stay free of activity lines"


def test_quiet_suppresses_all_tool_lines(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _feeding_input(["What time is it?"]))
    assert cli.main(["--quiet", "--db", str(tmp_path / "quiet.db")]) == 0
    captured = capsys.readouterr()
    assert "[tool]" not in captured.err
    assert "[memory]" not in captured.err


# --------------------------------------------------------------------------
# execute(): failures must be unambiguous to the model reading them
# --------------------------------------------------------------------------


def test_success_is_marked_ok():
    payload = json.loads(tools.execute("calculate", {"expression": "2 + 2"}))
    assert payload == {"status": "ok", "result": 4}


def test_raising_tool_is_marked_with_explicit_error_status():
    payload = json.loads(tools.execute("calculate", {"expression": "not arithmetic"}))
    assert payload["status"] == "error"
    assert "result" not in payload
    assert payload["error"]["message"].startswith("Tool call failed")
    assert "calculate" in payload["error"]["message"]


def test_unknown_tool_is_marked_with_explicit_error_status():
    payload = json.loads(tools.execute("not_a_tool", {}))
    assert payload["status"] == "error"
    assert payload["error"]["type"] == "unknown_tool"
    assert payload["error"]["message"].startswith("Tool call failed")


def test_unapproved_dangerous_tool_is_marked_with_explicit_error_status():
    payload = json.loads(tools.execute("run_shell", {"command": "echo no"}))
    assert payload["status"] == "error"
    assert payload["error"]["type"] == "approval_required"


# --------------------------------------------------------------------------
# remember_fact: normalise instead of reject
# --------------------------------------------------------------------------


def test_kind_fact_is_stored_as_semantic(dream, store):
    result = _remember({"content": "کاربر پایتون کار می‌کند", "kind": "fact"})
    assert result["kind"] == "semantic"
    stored = store.get(result["id"])
    assert stored is not None and stored.kind == "semantic"


def test_empty_kind_is_stored_as_semantic(dream, store):
    result = _remember({"content": "کاربر قهوه تلخ دوست دارد", "kind": ""})
    assert result["kind"] == "semantic"
    assert store.get(result["id"]) is not None


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("semantic", "semantic"),
        ("EPISODIC", "episodic"),  # case is folded
        (" episodic ", "episodic"),  # whitespace is stripped
        ("preference", "semantic"),
        ("info", "semantic"),
        ("profile", "semantic"),
        ("event", "episodic"),
        ("episode", "episodic"),
        ("rule", "procedural"),
        ("instruction", "procedural"),
        ("howto", "procedural"),
        ("user_fact", "semantic"),  # unrecognised falls back, never rises
        ("gibberish", "semantic"),
    ],
)
def test_kind_is_normalised_not_rejected(dream, store, given, expected):
    result = _remember({"content": f"واقعیت نمونه برای {given}", "kind": given})
    assert result["kind"] == expected
    assert store.get(result["id"]) is not None


def test_importance_is_clamped_from_above(dream, store):
    result = _remember({"content": "اهمیت بیش از حد بزرگ", "importance": 5})
    assert result["importance"] == pytest.approx(1.0)
    assert store.get(result["id"]).importance == pytest.approx(1.0)


def test_importance_accepts_numeric_string(dream, store):
    result = _remember({"content": "اهمیت به شکل رشته عددی", "importance": "0.8"})
    assert result["importance"] == pytest.approx(0.8)
    assert store.get(result["id"]).importance == pytest.approx(0.8)


def test_importance_defaults_when_uninterpretable(dream, store):
    result = _remember({"content": "اهمیت ناخوانا", "importance": "very important"})
    assert result["importance"] == pytest.approx(0.5)


def test_end_to_end_sloppy_call_still_leaves_a_queryable_memory(store):
    backend = ScriptedBackend(
        [("remember_fact", {"content": "کاربر ماهی نمی‌خورد", "kind": "fact", "importance": "0.8"})]
    )
    turn = Dream(store, backend).run("من ماهی نمی‌خورم")
    assert len(turn.memories_created) == 1
    assert turn.tool_calls[0]["result"].startswith('{"status": "ok"')
    assert store.recall("ماهی"), "the normalised call must land in the store, not be dropped"


# --------------------------------------------------------------------------
# tools/memory_probe.py: a committed, repeatable diagnostic
# --------------------------------------------------------------------------


def test_probe_reports_no_tool_call_against_prose_only_backend():
    report = memory_probe.run_probe(EchoBackend())
    assert report.tool_calls == []
    assert report.memories_after == 0
    assert "no tool call emitted" in report.verdict
    assert not report.ok


def test_probe_reports_success_against_remembering_backend():
    backend = ScriptedBackend(
        [("remember_fact", {"content": "کاربر روی یک استارتاپ فین‌تک کار می‌کند", "kind": "fact"})]
    )
    report = memory_probe.run_probe(backend)
    assert report.memories_after == 1
    assert "memory stored successfully" in report.verdict
    assert report.ok
    text = report.render()
    assert "remember_fact" in text
    assert "arguments:" in text
    assert "result:" in text
    assert "memories in store after turn: 1" in text


def test_probe_reports_failed_call_when_the_tool_errors():
    backend = ScriptedBackend([("remember_fact", {"content": "", "kind": "semantic"})])
    report = memory_probe.run_probe(backend)
    assert report.memories_after == 0
    assert "tool call failed" in report.verdict
    assert not report.ok


def test_probe_main_runs_offline_and_exits_nonzero_on_failure(capsys):
    code = memory_probe.main(["--backend", "echo"])
    assert code == 1
    out = capsys.readouterr().out
    assert "no tool call emitted" in out
    assert "memories in store after turn: 0" in out
    assert "verdict:" in out
