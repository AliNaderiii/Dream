#!/usr/bin/env python3
"""apply_pr17.py - Standalone installer for Phase 14 / PR #17:
Interactive Terminal User Interface (TUI), Rich Colorizer, Approval Dialog & REPL Engine.

This installer creates or updates the following files in the target repository:
  - dream/tui/__init__.py
  - dream/tui/approval.py
  - dream/tui/banner.py
  - dream/tui/colors.py
  - dream/tui/formatters.py
  - dream/tui/prompter.py
  - dream/tui/repl.py
  - tests/test_tui_interactive_system.py
"""

from __future__ import annotations

import sys
from pathlib import Path

TUI_INIT = '''"""Dream Interactive Terminal User Interface (TUI) package."""

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
'''

TUI_APPROVAL = '''"""Interactive terminal approval dialog for guarded and dangerous actions."""

from __future__ import annotations

from typing import Any

from dream.tui.colors import ColorManager


class TerminalApprovalPrompt:
    """Prompts the user interactively in TUI for authorization of guarded actions."""

    def __init__(self, colors: ColorManager | None = None) -> None:
        self.colors = colors or ColorManager()

    def request_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: str = "guarded",
    ) -> bool:
        """Display authorization prompt and read user decision."""
        cm = self.colors
        badge = (
            cm.red("[DANGEROUS ACTION]")
            if risk_level == "dangerous"
            else cm.yellow("[GUARDED ACTION]")
        )

        prompt_box = [
            f"\\n{badge} {cm.bold('مجوز اجرای ابزار / Tool Execution Approval Required')}",
            cm.dim("─" * 60),
            f"  • {cm.bold('ابزار / Tool:')}      {cm.cyan(tool_name)}",
            f"  • {cm.bold('سطح ریسک / Risk:')} {cm.bold(risk_level.upper())}",
            f"  • {cm.bold('پارامترها / Args:')}  {arguments}",
            cm.dim("─" * 60),
            (
                f"  {cm.green('[y] Allow Once (تأیید)')}  |  "
                f"{cm.red('[n] Deny (رد)')}  |  {cm.dim('[a] Always Allow')}"
            ),
        ]

        print("\\n".join(prompt_box))
        try:
            choice = input(cm.yellow("انتخاب شما / Choice [y/n/a] (default: n): ")).strip().lower()
            if choice in ("y", "yes", "a", "always"):
                print(cm.green("✓ مجوز صادر شد. / Approved.\\n"))
                return True
            print(cm.red("✗ درخواست لغو شد. / Denied.\\n"))
            return False
        except (EOFError, KeyboardInterrupt):
            print(cm.red("\\n✗ عملیات متوقف شد. / Cancelled.\\n"))
            return False
'''

TUI_BANNER = r'''"""Bilingual ASCII banner and terminal status telemetry header."""

from __future__ import annotations

from typing import Any

from dream.tui.colors import ColorManager

_BANNER_ART = r"""
  ____                               
 |  _ \ _ __ ___  __ _ _ __ ___  
 | | | | '__/ _ \/ _` | '_ ` _ \ 
 | |_| | | |  __/ (_| | | | | | |
 |____/|_|  \___|\__,_|_| |_| |_|
"""

DREAM_VERSION = "2.0.0"


def render_banner(
    owner: str = "",
    model: str = "echo",
    backend_info: str = "EchoBackend",
    context_files_count: int = 4,
    colors: ColorManager | None = None,
) -> str:
    """Render the startup banner with telemetry info and bilingual greeting."""
    cm = colors or ColorManager()
    lines: list[str] = []

    # Styled ASCII art
    art_colored = cm.cyan(_BANNER_ART.strip("\n"))
    lines.append(art_colored)

    # Title & Version
    title = f"Dream Assistant v{DREAM_VERSION} — Next-Gen Agent Engine"
    lines.append(cm.bold(title))
    lines.append(cm.dim("=" * len(title)))

    # Status Telemetry Card
    owner_str = owner if owner else "Local Owner"
    lines.append(f"  {cm.dim('•')} {cm.bold('Owner:')}          {owner_str}")
    lines.append(
        f"  {cm.dim('•')} {cm.bold('Backend / Model:')} {cm.green(model)} ({backend_info})"
    )
    lines.append(
        f"  {cm.dim('•')} {cm.bold('Context Memory:')} "
        f"{context_files_count} Tier-4 Files (SOUL, USER, MEMORY, AGENTS)"
    )
    lines.append(f"  {cm.dim('•')} {cm.bold('Security Floor:')} L1-L5 Multi-Layer Guard Active")

    # Bilingual Quick Start
    lines.append("")
    lines.append(
        f"  {cm.yellow('💡 راهنما:')} دستورات با {cm.cyan('/help')} | خروج با {cm.dim('/exit')}"
    )
    lines.append("")
    return "\n".join(lines)


def render_status_bar(telemetry: dict[str, Any], colors: ColorManager | None = None) -> str:
    """Render a one-line live status bar for the prompt footer."""
    cm = colors or ColorManager()
    model = telemetry.get("model", "default")
    turns = telemetry.get("turns", 0)
    memory_tokens = telemetry.get("memory_tokens", 0)
    return cm.dim(f"[{model} | Turns: {turns} | Context: {memory_tokens} chars]")
'''

TUI_COLORS = '''"""ANSI color management, terminal capability detection, and text styling."""

from __future__ import annotations

import os
import sys
from typing import TextIO


class ColorManager:
    """Detects terminal capabilities and formats styled text."""

    def __init__(
        self,
        stream: TextIO | None = None,
        force_color: bool = False,
        no_color: bool = False,
    ) -> None:
        self.stream = stream or sys.stdout
        self._force_color = force_color
        self._no_color = no_color or bool(os.environ.get("NO_COLOR", "").strip())
        self._term = os.environ.get("TERM", "").lower()

    @property
    def is_enabled(self) -> bool:
        if self._no_color:
            return False
        if self._force_color:
            return True
        if self._term == "dumb":
            return False
        try:
            return hasattr(self.stream, "isatty") and self.stream.isatty()
        except Exception:
            return False

    def style(self, text: str, code: str) -> str:
        """Wrap text in ANSI escape sequence if terminal supports color."""
        if not self.is_enabled:
            return text
        return f"\\x1b[{code}m{text}\\x1b[0m"

    def bold(self, text: str) -> str:
        return self.style(text, "1")

    def dim(self, text: str) -> str:
        return self.style(text, "2")

    def italic(self, text: str) -> str:
        return self.style(text, "3")

    def underline(self, text: str) -> str:
        return self.style(text, "4")

    def red(self, text: str) -> str:
        return self.style(text, "31")

    def green(self, text: str) -> str:
        return self.style(text, "32")

    def yellow(self, text: str) -> str:
        return self.style(text, "33")

    def blue(self, text: str) -> str:
        return self.style(text, "34")

    def magenta(self, text: str) -> str:
        return self.style(text, "35")

    def cyan(self, text: str) -> str:
        return self.style(text, "36")

    def white(self, text: str) -> str:
        return self.style(text, "37")

    def render_meter(self, value: int, maximum: int, width: int = 15) -> str:
        """Render a visual gauge bar e.g. [■■■■■□□□□□] (1200/2000)."""
        if maximum <= 0:
            return f"[{'■' * width}] ({value})"
        ratio = min(max(value / maximum, 0.0), 1.0)
        filled = int(round(ratio * width))
        empty = width - filled
        bar = "■" * filled + "□" * empty
        pct = int(ratio * 100)
        if ratio > 0.9:
            colored_bar = self.red(bar)
        elif ratio > 0.7:
            colored_bar = self.yellow(bar)
        else:
            colored_bar = self.green(bar)
        return f"[{colored_bar}] {value}/{maximum} ({pct}%)"


# Default global color manager instance
_DEFAULT_MANAGER = ColorManager()


def style(text: str, code: str, stream: TextIO | None = None) -> str:
    """Convenience functional wrapper matching existing Dream API."""
    mgr = ColorManager(stream) if stream is not None else _DEFAULT_MANAGER
    return mgr.style(text, code)
'''

TUI_FORMATTERS = '''"""Rich text and visual formatters for tools, memory, subagents, and context files."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from dream.tui.colors import ColorManager


def truncate_text(text: str, limit: int = 120) -> str:
    """Truncate text safely with ellipsis."""
    text_clean = text.replace("\\n", " ").strip()
    if len(text_clean) <= limit:
        return text_clean
    return text_clean[: limit - 3] + "..."


def format_tool_line(
    name: str,
    arguments: dict[str, Any],
    result: str,
    colors: ColorManager | None = None,
) -> str:
    """Format a tool invocation and outcome line."""
    cm = colors or ColorManager()
    status_icon, status_label = _call_status(result)

    args_rendered = ", ".join(
        f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in arguments.items()
    )
    truncated_args = truncate_text(args_rendered, 60)
    truncated_result = truncate_text(result, 80)

    if status_icon == "✓":
        tag = cm.green(f"[{status_label}]")
    elif status_icon == "✗":
        tag = cm.red(f"[{status_label}]")
    else:
        tag = cm.yellow(f"[{status_label}]")

    return f"{tag} {cm.bold(name)}({truncated_args}) → {truncated_result}"


def _call_status(result: str) -> tuple[str, str]:
    """Classify tool result into icon and label."""
    try:
        parsed = json.loads(result)
        if isinstance(parsed, dict) and parsed.get("status") == "error":
            return "✗", "tool:error"
    except Exception:
        pass
    if "refused" in result.lower() or "denied" in result.lower():
        return "!", "tool:refused"
    return "✓", "tool:ok"


def format_extraction_line(result: Any, colors: ColorManager | None = None) -> str:
    """Format memory extraction outcome."""
    cm = colors or ColorManager()
    if not result:
        return cm.dim("[memory] no facts extracted")
    if isinstance(result, list):
        items = [truncate_text(str(r), 50) for r in result]
        return cm.cyan(f"[memory:learned] {len(result)} facts: {', '.join(items)}")
    return cm.cyan(f"[memory:learned] {truncate_text(str(result), 80)}")


def format_context_files_table(
    files_usage: dict[str, dict[str, Any]],
    colors: ColorManager | None = None,
) -> str:
    """Render a visual table with usage meters for Tier-4 context files."""
    cm = colors or ColorManager()
    lines = [
        cm.bold("📁 Tier-4 Persistent Context Files"),
        cm.dim("─" * 65),
    ]
    for filename, stats in files_usage.items():
        chars = stats.get("chars", 0)
        max_chars = stats.get("max_chars", 2000)
        description = stats.get("description", "")
        meter = cm.render_meter(chars, max_chars, width=15)
        lines.append(f"  {cm.bold(filename):<12} {meter:<30} {cm.dim(description)}")
    lines.append(cm.dim("─" * 65))
    return "\\n".join(lines)


def format_subagents_table(
    subagents_list: list[dict[str, Any]],
    colors: ColorManager | None = None,
) -> str:
    """Render subagents status table."""
    cm = colors or ColorManager()
    if not subagents_list:
        return cm.dim("No active subagent workflows currently running.")

    lines = [
        cm.bold("🤖 Subagents & Multi-Agent Swarm Status"),
        cm.dim("─" * 70),
        f"  {'ID':<10} {'Role':<15} {'Status':<12} {'Description':<30}",
        cm.dim("─" * 70),
    ]
    for sub in subagents_list:
        sub_id = sub.get("id", "sub-0")
        role = sub.get("role", "worker")
        status = sub.get("status", "idle")
        desc = truncate_text(sub.get("description", ""), 30)

        is_active = status in ("completed", "running")
        status_colored = cm.green(status) if is_active else cm.yellow(status)
        lines.append(f"  {sub_id:<10} {cm.bold(role):<15} {status_colored:<21} {desc:<30}")
    lines.append(cm.dim("─" * 70))
    return "\\n".join(lines)


def report_turn_activity(
    turn: Any,
    output: Callable[[str], None] | None = None,
    colors: ColorManager | None = None,
) -> None:
    """Report tool execution and extraction activity from a Turn to output."""
    out = output or print
    cm = colors or ColorManager()

    # Tool calls
    if hasattr(turn, "tool_calls") and turn.tool_calls:
        for call in turn.tool_calls:
            name = call.get("name", "unknown")
            args = call.get("arguments", {})
            result = str(call.get("result", ""))
            out(format_tool_line(name, args, result, cm))

    # Extraction
    if hasattr(turn, "extraction") and turn.extraction:
        out(format_extraction_line(turn.extraction, cm))
'''

TUI_PROMPTER = '''"""Interactive prompt reader with multiline support and autocomplete hints."""

from __future__ import annotations

import difflib

from dream.tui.colors import ColorManager


class TerminalPrompter:
    """Handles terminal user inputs, multiline lines, and command matching."""

    def __init__(self, colors: ColorManager | None = None) -> None:
        self.colors = colors or ColorManager()

    def get_prompt_symbol(self, multiline: bool = False) -> str:
        if multiline:
            return self.colors.dim("... ")
        return self.colors.cyan("dream> ")

    def read_input(self, known_commands: tuple[str, ...] = ()) -> str | None:
        """Read a single line or multiline block from stdin."""
        try:
            first_line = input(self.get_prompt_symbol(multiline=False))
        except (EOFError, KeyboardInterrupt):
            return None

        # Multiline continuation check (line ending in backslash)
        if first_line.endswith("\\\\"):
            lines = [first_line[:-1]]
            while True:
                try:
                    cont = input(self.get_prompt_symbol(multiline=True))
                except (EOFError, KeyboardInterrupt):
                    break
                if cont.endswith("\\\\"):
                    lines.append(cont[:-1])
                else:
                    lines.append(cont)
                    break
            return "\\n".join(lines)

        return first_line

    def suggest_command(self, query: str, known_commands: tuple[str, ...]) -> str | None:
        """Fuzzy match slash command."""
        matches = difflib.get_close_matches(query, known_commands, n=1, cutoff=0.55)
        return matches[0] if matches else None
'''

TUI_REPL = '''"""Interactive REPL session manager for Dream Assistant v2.0."""

from __future__ import annotations

from collections.abc import Callable

from dream.agent import Dream
from dream.memory import MemoryStore
from dream.tui.banner import render_banner
from dream.tui.colors import ColorManager
from dream.tui.formatters import report_turn_activity
from dream.tui.prompter import TerminalPrompter


class InteractiveSession:
    """Manages the interactive terminal loop, slash commands, and telemetry."""

    def __init__(
        self,
        dream: Dream,
        store: MemoryStore,
        owner: str = "",
        quiet: bool = False,
        colors: ColorManager | None = None,
        output: Callable[[str], None] = print,
    ) -> None:
        self.dream = dream
        self.store = store
        self.owner = owner
        self.quiet = quiet
        self.colors = colors or ColorManager()
        self.output = output
        self.prompter = TerminalPrompter(self.colors)
        self.turn_count = 0

    def start(self, show_banner: bool = True) -> None:
        """Start the interactive REPL loop."""
        if show_banner:
            model_name = getattr(self.dream.backend, "model", "default")
            backend_type = self.dream.backend.__class__.__name__
            banner_text = render_banner(
                owner=self.owner,
                model=model_name,
                backend_info=backend_type,
                context_files_count=4,
                colors=self.colors,
            )
            self.output(banner_text)

        # Check due reminders at startup
        try:
            due = self.store.check_due_reminders()
            if due and not self.quiet:
                for r in due:
                    self.output(self.colors.yellow(f"[⏰ Reminder] {r.text}"))
        except Exception:
            pass

        while True:
            raw_input = self.prompter.read_input()
            if raw_input is None:
                self.output("\\n" + self.colors.dim("Session terminated. Goodbye! / خدانگهدار"))
                break

            text = raw_input.strip()
            if not text:
                continue

            # Command routing
            if text.startswith(("/", "\\\\")):
                from dream.cli.commands import dispatch_command

                should_continue = dispatch_command(
                    text,
                    self.dream,
                    output=self.output,
                    quiet=self.quiet,
                    colors=self.colors,
                )
                if not should_continue:
                    break
                continue

            # Execute normal agent turn
            self.turn_count += 1
            try:
                turn = self.dream.run(text)
                if not self.quiet:
                    report_turn_activity(turn, output=self.output, colors=self.colors)
                self.output(turn.reply)
            except Exception as exc:
                self.output(self.colors.red(f"Error during agent turn: {exc}"))
'''

TEST_TUI_SYSTEM = '''"""Comprehensive test suite for Interactive TUI, ColorManager, Approval Dialog, and REPL."""

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
    assert "\\x1b[36m" in cm.cyan("Salam")
    assert "\\x1b[32m" in cm.green("Done")
    assert "\\x1b[31m" in cm.red("Error")

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
    lines = iter(["def add(a, b):\\\\", "    return a + b"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    result = prompter.read_input()
    assert result == "def add(a, b):\\n    return a + b"

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

        full_output = "\\n".join(outputs)
        assert "Dream Assistant v" in full_output
        assert "سلام دستیار هوشمند" in full_output
'''


def apply_patch(repo_dir: Path) -> None:
    print(f"[*] Applying PR #17 (Interactive TUI & REPL Engine) to: {repo_dir.resolve()}")

    files_to_write = {
        repo_dir / "dream" / "tui" / "__init__.py": TUI_INIT,
        repo_dir / "dream" / "tui" / "approval.py": TUI_APPROVAL,
        repo_dir / "dream" / "tui" / "banner.py": TUI_BANNER,
        repo_dir / "dream" / "tui" / "colors.py": TUI_COLORS,
        repo_dir / "dream" / "tui" / "formatters.py": TUI_FORMATTERS,
        repo_dir / "dream" / "tui" / "prompter.py": TUI_PROMPTER,
        repo_dir / "dream" / "tui" / "repl.py": TUI_REPL,
        repo_dir / "tests" / "test_tui_interactive_system.py": TEST_TUI_SYSTEM,
    }

    for path, content in files_to_write.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"  [+] Wrote: {path.relative_to(repo_dir)}")

    print("\n[✓] PR #17 successfully applied!")
    print("Next steps:")
    print("  1. Run tests: pytest -v tests/test_interactive_tui_and_cli.py tests/test_tui_interactive_system.py")
    print("  2. Run linter: ruff check dream/tui tests/test_tui_interactive_system.py")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    apply_patch(target)
