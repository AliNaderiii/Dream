"""Dream Interactive Terminal User Interface (TUI) package."""

from __future__ import annotations

from dream.tui.approval import TerminalApprovalPrompt
from dream.tui.banner import DREAM_VERSION, render_banner, render_status_bar
from dream.tui.colors import ColorManager, style
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

__all__ = [
    "DREAM_VERSION",
    "ColorManager",
    "InteractiveSession",
    "TerminalApprovalPrompt",
    "TerminalPrompter",
    "format_context_files_table",
    "format_extraction_line",
    "format_subagents_table",
    "format_tool_line",
    "render_banner",
    "render_status_bar",
    "report_turn_activity",
    "style",
    "truncate_text",
]
