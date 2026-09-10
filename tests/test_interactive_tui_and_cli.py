"""Tests for Interactive TUI, ColorManager, Banner, and Enhanced CLI Commands."""

from __future__ import annotations

import io
from types import SimpleNamespace

from dream.agent import Dream, EchoBackend
from dream.cli import (
    _PHONE_ALLOWED_CANONICAL,
    _PHONE_POLICY,
    _PHONE_REFUSED_CANONICAL,
    KNOWN_COMMANDS,
    PHONE_HELP,
    TERMINAL_HELP,
    dispatch_command,
)
from dream.memory import MemoryStore
from dream.tui import (
    ColorManager,
    InteractiveSession,
    TerminalPrompter,
    format_context_files_table,
    format_extraction_line,
    format_subagents_table,
    format_tool_line,
    render_banner,
    render_status_bar,
    report_turn_activity,
    truncate_text,
)


def test_color_manager_no_color_and_dumb_terminal(monkeypatch):
    buf = io.StringIO()
    cm = ColorManager(buf, no_color=True)
    assert not cm.is_enabled
    assert cm.bold("Dream") == "Dream"
    assert cm.cyan("Hello") == "Hello"

    _ = ColorManager(buf, force_color=False)
    monkeypatch.setenv("TERM", "dumb")
    assert not ColorManager(buf).is_enabled


def test_color_manager_force_color():
    buf = io.StringIO()
    cm = ColorManager(buf, force_color=True)
    assert cm.is_enabled
    assert "\x1b[1m" in cm.bold("Dream")
    assert "\x1b[36m" in cm.cyan("Hello")
    assert "\x1b[31m" in cm.red("Error")
    assert "\x1b[32m" in cm.green("OK")
    assert "\x1b[33m" in cm.yellow("Warn")


def test_color_manager_render_meter():
    cm = ColorManager(force_color=True)
    meter_low = cm.render_meter(500, 2000, width=10)
    assert "500/2000" in meter_low
    assert "25%" in meter_low

    meter_high = cm.render_meter(1900, 2000, width=10)
    assert "1900/2000" in meter_high
    assert "95%" in meter_high

    meter_zero = cm.render_meter(100, 0, width=10)
    assert "(100)" in meter_zero


def test_banner_and_status_bar_rendering():
    cm = ColorManager(force_color=False)
    banner = render_banner(
        owner="Ali",
        model="qwen2.5:7b",
        backend_info="OllamaBackend",
        context_files_count=4,
        colors=cm,
    )
    assert "Dream Assistant v" in banner
    assert "Ali" in banner
    assert "qwen2.5:7b" in banner
    assert "راهنما:" in banner

    status = render_status_bar({"model": "gpt-4o", "turns": 3, "memory_tokens": 1250}, cm)
    assert "gpt-4o" in status
    assert "Turns: 3" in status


def test_formatters_and_activity_reporting():
    cm = ColorManager(force_color=False)
    # Truncate
    assert truncate_text("short text", 20) == "short text"
    assert truncate_text("a" * 50, 10) == "aaaaaaa..."

    # Format tool line
    ok_line = format_tool_line("calc", {"expr": "2+2"}, '{"result": 4}', cm)
    assert "[tool:ok]" in ok_line
    assert "calc(" in ok_line

    err_line = format_tool_line("api", {}, '{"status": "error", "error": "fail"}', cm)
    assert "[tool:error]" in err_line

    refused_line = format_tool_line("shell", {}, "Dangerous tool was refused by user policy", cm)
    assert "[tool:refused]" in refused_line

    # Format extraction line
    no_fact = format_extraction_line(None, cm)
    assert "no facts extracted" in no_fact

    fact_str = format_extraction_line(["User prefers Persian", "User lives in Tehran"], cm)
    assert "2 facts" in fact_str

    # Tables
    files_stats = {
        "SOUL.md": {"chars": 1200, "max_chars": 2000, "description": "Core identity"},
        "USER.md": {"chars": 800, "max_chars": 1375, "description": "User profile"},
    }
    table = format_context_files_table(files_stats, cm)
    assert "SOUL.md" in table
    assert "USER.md" in table

    sub_table = format_subagents_table(
        [{"id": "sub-1", "role": "researcher", "status": "completed", "description": "Web search"}],
        cm,
    )
    assert "sub-1" in sub_table
    assert "researcher" in sub_table

    empty_sub = format_subagents_table([], cm)
    assert "No active subagent" in empty_sub

    # Report turn activity
    reported: list[str] = []
    dummy_turn = SimpleNamespace(
        reply="Hello",
        tool_calls=[{"name": "test_tool", "arguments": {"x": 1}, "result": "ok"}],
        extraction=["Learned something"],
    )
    report_turn_activity(dummy_turn, output=reported.append, colors=cm)
    assert len(reported) == 2


def test_prompter_suggestions():
    prompter = TerminalPrompter()
    known = ("/model", "/context", "/compress", "/subagents", "/skills", "/help")
    assert prompter.suggest_command("/modle", known) == "/model"
    assert prompter.suggest_command("/skil", known) == "/skills"


def test_dispatch_new_commands(tmp_path):
    db_path = str(tmp_path / "test_cli.db")
    with MemoryStore(db_path) as store:
        dream = Dream(store, EchoBackend())
        out: list[str] = []

        # /model
        dispatch_command("/model", dream, output=out.append)
        assert any("Active Backend:" in line for line in out)

        out.clear()
        dispatch_command("/model echo", dream, output=out.append)
        assert any("Successfully switched backend" in line for line in out)

        # /context
        out.clear()
        dispatch_command("/context", dream, output=out.append)
        assert any("Tier-4 Persistent Context Files" in line for line in out)

        # /compress
        out.clear()
        dispatch_command("/compress", dream, output=out.append)
        assert any("compress" in line.lower() for line in out)

        # /subagents
        out.clear()
        dispatch_command("/subagents", dream, output=out.append)
        assert any("Subagents" in line for line in out)

        # /insights
        out.clear()
        dispatch_command("/insights", dream, output=out.append)
        assert any("Intelligence & Recall Insights" in line for line in out)

        # /clear alias
        out.clear()
        dispatch_command("/clear", dream, output=out.append)
        assert any("Session context cleared" in line for line in out)


def test_phone_and_terminal_parity_remains_intact():
    """Verify phone policy consistency with newly added commands."""
    assert _PHONE_REFUSED_CANONICAL == frozenset({"/dedupe", "/pin", "/exit"})
    for cmd in KNOWN_COMMANDS:
        assert cmd in _PHONE_POLICY, f"{cmd} missing phone policy entry"
        allowed, reason = _PHONE_POLICY[cmd]
        assert isinstance(allowed, bool)
        if not allowed:
            assert len(reason.strip()) > 10

    # Ensure all canonical allowed commands are in phone help
    for cmd in _PHONE_ALLOWED_CANONICAL:
        assert cmd in PHONE_HELP
    assert "/exit" not in PHONE_HELP
    assert "/exit" in TERMINAL_HELP


def test_interactive_session_lifecycle(tmp_path, monkeypatch):
    db_path = str(tmp_path / "session.db")
    with MemoryStore(db_path) as store:
        dream = Dream(store, EchoBackend())
        inputs = iter(["/model", "Salam!", "/exit"])
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
        assert "Active Backend:" in full_output
        assert "Salam!" in full_output
