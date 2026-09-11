"""Comprehensive test suite for Interactive TUI, ColorManager, Approval Dialog, and REPL."""

from __future__ import annotations

from types import SimpleNamespace

from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore
from dream.tui.approval import TerminalApprovalPrompt
from dream.tui.banner import render_banner, render_status_bar
from dream.tui.colors import ColorManager
from dream.tui.formatters import (
    format_context_files_table,
    format_extraction_line,
    format_subagents_table,
    format_tool_line,
    report_turn_activity,
    truncate_text,
)
from dream.tui.prompter import TerminalPrompter
from dream.tui.repl import InteractiveSession


def test_tui_color_manager_rendering():
    """Verify ANSI coloring, text styling, and meter gauges."""
    cm = ColorManager(force_color=True)
    assert cm.is_enabled is True
    assert "\x1b[36m" in cm.cyan("Salam")
    assert "\x1b[32m" in cm.green("Done")
    assert "\x1b[31m" in cm.red("Error")

    meter_str = cm.render_meter(750, 1000, width=10)
    assert "750/1000" in meter_str
    assert "75%" in meter_str


def test_tui_banner_and_status_bar():
    """Verify startup banner and telemetry footer."""
    cm = ColorManager(force_color=False)
    banner = render_banner(
        owner="Ali Naderi",
        model="qwen2.5:14b",
        backend_info="OllamaBackend",
        context_files_count=4,
        colors=cm,
    )
    assert "Dream Assistant v" in banner
    assert "Ali Naderi" in banner
    assert "qwen2.5:14b" in banner

    status = render_status_bar({"model": "gpt-4o", "turns": 5, "memory_tokens": 1400}, cm)
    assert "gpt-4o" in status
    assert "Turns: 5" in status


def test_tui_terminal_prompter_and_multiline(monkeypatch):
    """Verify prompter reading, multiline continuations, and suggestions."""
    cm = ColorManager(force_color=False)
    prompter = TerminalPrompter(cm)

    # Prompt symbol
    assert "dream> " in prompter.get_prompt_symbol(multiline=False)
    assert "... " in prompter.get_prompt_symbol(multiline=True)

    # Multiline input simulation
    lines = iter(["def add(a, b):\\", "    return a + b"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    result = prompter.read_input()
    assert result == "def add(a, b):\n    return a + b"

    # Command fuzzy matching
    known = ("/model", "/context", "/compress", "/subagents", "/skills", "/mcp")
    assert prompter.suggest_command("/modl", known) == "/model"
    assert prompter.suggest_command("/sub", known) == "/subagents"


def test_tui_approval_prompt(monkeypatch):
    """Verify interactive tool execution approval dialog."""
    cm = ColorManager(force_color=False)
    approver = TerminalApprovalPrompt(cm)

    # Allow Once
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert approver.request_approval("run_shell", {"cmd": "ls -la"}, "guarded") is True

    # Deny
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert approver.request_approval("run_shell", {"cmd": "rm -rf /"}, "dangerous") is False

    # Always Allow
    monkeypatch.setattr("builtins.input", lambda prompt="": "a")
    assert approver.request_approval("write_file", {"path": "app.py"}, "guarded") is True


def test_tui_formatters_and_activity():
    """Verify tool, memory extraction, and table formatters."""
    cm = ColorManager(force_color=False)

    # Tool lines
    ok_line = format_tool_line("calculate", {"expr": "5*5"}, '{"result": 25}', cm)
    assert "[tool:ok]" in ok_line
    assert "calculate(" in ok_line

    # Truncation
    assert truncate_text("short", 10) == "short"
    assert truncate_text("very long text string", 10) == "very lo..."

    # Extractions
    no_ext = format_extraction_line(None, cm)
    assert "no facts" in no_ext
    with_ext = format_extraction_line(["User preference noted"], cm)
    assert "1 fact" in with_ext

    # Tables
    files_stats = {
        "SOUL.md": {"chars": 1500, "max_chars": 2200, "description": "Agent Soul"},
        "USER.md": {"chars": 900, "max_chars": 1375, "description": "User Profile"},
    }
    table = format_context_files_table(files_stats, cm)
    assert "SOUL.md" in table
    assert "USER.md" in table

    sub_table = format_subagents_table(
        [
            {
                "id": "sub-test",
                "role": "researcher",
                "status": "active",
                "description": "Analyzing code",
            }
        ],
        cm,
    )
    assert "sub-test" in sub_table
    assert "researcher" in sub_table

    # Turn activity report
    reported: list[str] = []
    dummy_turn = SimpleNamespace(
        reply="Final Answer",
        tool_calls=[{"name": "fetch", "arguments": {"u": "http"}, "result": "done"}],
        extraction=["Extracted fact"],
    )
    report_turn_activity(dummy_turn, output=reported.append, colors=cm)
    assert len(reported) == 2


def test_interactive_session_repl_loop(tmp_path, monkeypatch):
    """Verify complete REPL session interaction."""
    db_path = str(tmp_path / "repl_test.db")
    with MemoryStore(db_path) as store:
        dream = Dream(store, EchoBackend())
        inputs = iter(["سلام دستیار هوشمند", "/exit"])
        outputs: list[str] = []

        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

        session = InteractiveSession(
            dream=dream,
            store=store,
            owner="Ali",
            quiet=True,
            output=outputs.append,
        )
        session.start(show_banner=True)

        full_output = "\n".join(outputs)
        assert "Dream Assistant v" in full_output
        assert "سلام دستیار هوشمند" in full_output
