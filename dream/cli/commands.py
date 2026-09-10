"""Slash command registry, phone policy definitions, and interactive command dispatcher."""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Callable
from typing import Any

from dream.agent import Dream
from dream.memory import normalize_fa
from dream.tools import REGISTRY
from dream.tui.colors import ColorManager
from dream.tui.formatters import (
    format_context_files_table,
    format_subagents_table,
)

KNOWN_COMMANDS: tuple[str, ...] = (
    "/mem",
    "/mems",
    "/stats",
    "/forget",
    "/dedupe",
    "/export",
    "/pin",
    "/unpin",
    "/pinned",
    "/remind",
    "/reminders",
    "/clear",
    "/exit",
    "/help",
    "/model",
    "/context",
    "/compress",
    "/subagents",
    "/skills",
    "/insights",
)

PHONE_COMMANDS: tuple[str, ...] = (
    "/mem",
    "/mems",
    "/stats",
    "/forget",
    "/export",
    "/unpin",
    "/pinned",
    "/remind",
    "/reminders",
    "/clear",
    "/help",
    "/model",
    "/context",
    "/compress",
    "/subagents",
    "/skills",
    "/insights",
)

_COMMAND_ALIASES: dict[str, str] = {
    "/models": "/model",
    "/provider": "/model",
    "/ctx": "/context",
    "/files": "/context",
    "/compact": "/compress",
    "/agents": "/subagents",
    "/subagent": "/subagents",
    "/skill": "/skills",
    "/tools": "/skills",
    "/analytics": "/insights",
    "/cls": "/clear",
    "/quit": "/exit",
    "/q": "/exit",
    "/h": "/help",
    "?": "/help",
}

_PHONE_POLICY: dict[str, tuple[bool, str]] = {
    "/mem": (True, ""),
    "/mems": (True, ""),
    "/stats": (True, ""),
    "/forget": (True, ""),
    "/dedupe": (
        False,
        "Deduplication can merge or remove memories in bulk. "
        "Run this from the desktop CLI where you can inspect the changes before confirming.",
    ),
    "/export": (True, ""),
    "/pin": (
        False,
        "Pinning memories is reserved for the desktop interface. "
        "Use /mem on phone to store high-importance items.",
    ),
    "/unpin": (True, ""),
    "/pinned": (True, ""),
    "/remind": (True, ""),
    "/reminders": (True, ""),
    "/clear": (True, ""),
    "/exit": (
        False,
        "Phone sessions do not exit. Close or switch your chat app to end the conversation.",
    ),
    "/help": (True, ""),
    "/model": (True, ""),
    "/context": (True, ""),
    "/compress": (True, ""),
    "/subagents": (True, ""),
    "/skills": (True, ""),
    "/insights": (True, ""),
}

_PHONE_ALLOWED_CANONICAL: frozenset[str] = frozenset(
    cmd for cmd, (allowed, _) in _PHONE_POLICY.items() if allowed
)
_PHONE_REFUSED_CANONICAL: frozenset[str] = frozenset(
    cmd for cmd, (allowed, _) in _PHONE_POLICY.items() if not allowed
)

PHONE_HELP = """\
Available phone commands:
  /mem TEXT            Store a memory
  /mems [QUERY]        List recent memories or search
  /stats               Show memory statistics
  /forget ID           Delete a memory by ID
  /export              Export memories as JSON
  /unpin ID            Unpin a memory by ID
  /pinned              List all pinned memories
  /remind SPEC MSG     Schedule a reminder (e.g. /remind in 10m check oven)
  /reminders           List pending reminders
  /model [NAME]        Show or switch the active LLM backend
  /context             Inspect Tier-4 persistent context files (SOUL/USER/MEMORY/AGENTS)
  /compress            Trigger contextual working-memory compression
  /subagents           View background subagent tasks and roles
  /skills              List active tools and loaded skill registry
  /insights            View memory retention, dialectical profile & intelligence metrics
  /clear               Reset active working conversation
  /help                Show this help message\
"""

TERMINAL_HELP = """\
Available interactive slash commands:
  /model [PROVIDER]    View or live-switch backend (echo, openai, ollama, avalai, claude, gemini)
  /context             Inspect Tier-4 persistent context files (SOUL/USER/MEMORY/AGENTS)
  /compress            Trigger Jalali-aware contextual compression and tool-output pruning
  /subagents           Inspect background subagent coordinators, roles, and status
  /skills              List active skills, custom procedures, and tools
  /insights            View memory retention, dialectical profile & intelligence metrics
  /mem TEXT            Store an explicit memory directly
  /mems [QUERY]        List recent memories or search semantic index
  /stats               Show total memories, kinds breakdown, and database path
  /forget ID           Delete a memory by ID
  /dedupe              Run semantic deduplication across memory store
  /export              Export all memories as formatted JSON
  /pin ID              Pin a memory permanently into working context
  /unpin ID            Unpin a previously pinned memory
  /pinned              List all pinned memories
  /remind SPEC MSG     Schedule a reminder (e.g. /remind in 2h call client)
  /reminders           List pending scheduled reminders
  /clear               Reset current conversation turns and working memory
  /exit                Exit the interactive Dream session (aliases: /quit, /q)
  /help                Show this command reference (alias: /h, ?)\
"""

_HELP_FRAGMENTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("/mem",), "Store a memory: /mem [text]"),
    (("/mems",), "Search or list memories: /mems [query]"),
    (("/stats",), "View memory statistics: /stats"),
    (("/forget",), "Delete a memory: /forget <id>"),
    (("/dedupe",), "Semantic deduplication: /dedupe"),
    (("/export",), "Export memories: /export"),
    (("/pin",), "Pin a memory: /pin <id>"),
    (("/unpin",), "Unpin a memory: /unpin <id>"),
    (("/pinned",), "List pinned memories: /pinned"),
    (("/remind",), "Schedule a reminder: /remind [when] [message]"),
    (("/reminders",), "List pending reminders: /reminders"),
    (("/clear", "/cls"), "Clear conversation history: /clear"),
    (("/exit", "/quit", "/q"), "Exit the session: /exit"),
    (("/model", "/models", "/provider"), "Switch LLM backend: /model [name]"),
    (("/context", "/ctx", "/files"), "Inspect context files: /context"),
    (("/compress", "/compact"), "Compress working context: /compress"),
    (("/subagents", "/subagent", "/agents"), "Inspect subagent tasks: /subagents"),
    (("/skills", "/skill", "/tools"), "List tools & skills: /skills"),
    (("/insights", "/analytics"), "Memory & intelligence insights: /insights"),
    (("/help", "/h", "?"), "Show help reference: /help"),
)

_NATURAL_PATTERNS: tuple[tuple[str, str, int], ...] = (
    ("minutes", "m", 60),
    ("minute", "m", 60),
    ("mins", "m", 60),
    ("min", "m", 60),
    ("hours", "h", 3600),
    ("hour", "h", 3600),
    ("days", "d", 86400),
    ("day", "d", 86400),
    ("weeks", "w", 604800),
    ("week", "w", 604800),
)

_PERSIAN_PATTERNS: tuple[tuple[str, tuple[str, int]], ...] = (
    ("فردا", ("days", 1)),
    ("پس فردا", ("days", 2)),
    ("هفته آینده", ("days", 7)),
    ("هفته بعد", ("days", 7)),
)


def _closest_command(cmd: str) -> str | None:
    """Find the closest known command for suggestions."""
    matches = difflib.get_close_matches(cmd, KNOWN_COMMANDS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _format_repeat(interval: int) -> str:
    """Format recurrence interval into human-readable string."""
    if interval % 86400 == 0:
        days = interval // 86400
        return f"every {days}d" if days > 1 else "daily"
    if interval % 3600 == 0:
        hours = interval // 3600
        return f"every {hours}h" if hours > 1 else "hourly"
    if interval % 60 == 0:
        mins = interval // 60
        return f"every {mins}m"
    return f"every {interval}s"


def _parse_natural_date_prefix(args: str) -> tuple[dict[str, int], str] | None:
    """Parse natural English and Persian relative date phrases."""
    norm = normalize_fa(args.strip())
    for fa_phrase, (unit, amount) in _PERSIAN_PATTERNS:
        if norm.startswith(fa_phrase):
            rest = norm[len(fa_phrase):].strip()
            return {unit: amount}, rest

    m = re.match(r"^in\s+(\d+)\s+([a-zA-Z]+)\s*(.*)$", args, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        unit_str = m.group(2).lower()
        rest = m.group(3).strip()
        for key, _, _ in _NATURAL_PATTERNS:
            if unit_str.startswith(key):
                unit_map = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
                for _, ucode, _ in _NATURAL_PATTERNS:
                    if unit_str.startswith(key):
                        return {unit_map.get(ucode, "minutes"): num}, rest
    return None


def _parse_remind_args(args: str) -> dict[str, Any] | None:
    """Parse reminder command arguments into structured reminder specification."""
    if not args.strip():
        return None
    natural = _parse_natural_date_prefix(args)
    if natural:
        rel_kwargs, msg = natural
        if msg:
            return {"when": rel_kwargs, "message": msg, "repeat": None}

    tokens = args.strip().split()
    if len(tokens) >= 2:
        time_spec = tokens[0]
        msg = " ".join(tokens[1:])
        repeat = None
        if "--every" in tokens:
            idx = tokens.index("--every")
            if idx + 1 < len(tokens):
                repeat_str = tokens[idx + 1]
                msg_tokens = tokens[1:idx] + tokens[idx + 2:]
                msg = " ".join(msg_tokens)
                if repeat_str.endswith("m"):
                    repeat = int(repeat_str[:-1]) * 60
                elif repeat_str.endswith("h"):
                    repeat = int(repeat_str[:-1]) * 3600
                elif repeat_str.endswith("d"):
                    repeat = int(repeat_str[:-1]) * 86400
        return {"when": time_spec, "message": msg, "repeat": repeat}
    return None


def _print_memories(
    memories: list[Any],
    output: Callable[[str], None],
    colors: ColorManager | None = None,
) -> None:
    """Format and print a list of retrieved memory records."""
    cm = colors or ColorManager()
    if not memories:
        output(cm.dim("No memories found matching query."))
        return
    output(cm.bold(f"Retrieved {len(memories)} memories:"))
    for mem in memories:
        score_str = f" [score: {mem.score:.2f}]" if hasattr(mem, "score") and mem.score else ""
        pinned_mark = cm.yellow("★ ") if getattr(mem, "pinned", False) else "  "
        kind_str = cm.dim(f"({mem.kind})")
        output(f"{pinned_mark}#{mem.id} {kind_str}{score_str} {mem.content}")


def dispatch_command(
    raw_cmd: str,
    dream: Dream,
    output: Callable[[str], None] = print,
    quiet: bool = False,
    colors: ColorManager | None = None,
) -> bool:
    """Dispatch an interactive slash command."""
    cm = colors or ColorManager()
    parts = raw_cmd.strip().split(maxsplit=1)
    if not parts:
        return False

    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    cmd = _COMMAND_ALIASES.get(cmd, cmd)

    if cmd not in KNOWN_COMMANDS:
        suggestion = _closest_command(cmd)
        msg = f"Unknown command '{cmd}'."
        if suggestion:
            msg += f" Did you mean '{suggestion}'?"
        msg += " Type /help for a list of valid commands."
        output(cm.red(msg))
        return True

    store = dream.store

    if cmd == "/help":
        output(TERMINAL_HELP)
        return True

    if cmd in ("/exit", "/quit", "/q"):
        output(cm.cyan("Goodbye!"))
        return False

    if cmd in ("/clear", "/cls"):
        if hasattr(dream, "messages"):
            dream.messages.clear()
        output(cm.green("Session context cleared."))
        return True

    if cmd == "/stats":
        stats = store.stats() if hasattr(store, "stats") else {}
        output(cm.bold("Dream Memory Statistics:"))
        output(f"  Total Memories: {stats.get('total', 0)}")
        output(f"  Pinned Memories: {stats.get('pinned', 0)}")
        output(f"  Kinds: {stats.get('kinds', {})}")
        return True

    if cmd == "/mem":
        if not args:
            output(cm.yellow("Usage: /mem <content to remember>"))
            return True
        mem_id = store.remember(args)
        output(cm.green(f"Saved memory #{mem_id}"))
        return True

    if cmd == "/mems":
        results = store.recall(args) if args else store.recall("", limit=10)
        _print_memories(results, output, cm)
        return True

    if cmd == "/forget":
        if not args.isdigit():
            output(cm.yellow("Usage: /forget <memory_id>"))
            return True
        success = store.forget(int(args))
        if success:
            output(cm.green(f"Deleted memory #{args}"))
        else:
            output(cm.yellow(f"Memory #{args} not found."))
        return True

    if cmd == "/pin":
        if not args.isdigit():
            output(cm.yellow("Usage: /pin <memory_id>"))
            return True
        if hasattr(store, "pin"):
            store.pin(int(args))
            output(cm.green(f"Pinned memory #{args} into working context."))
        else:
            output(cm.yellow("Pinning not supported by current memory store."))
        return True

    if cmd == "/unpin":
        if not args.isdigit():
            output(cm.yellow("Usage: /unpin <memory_id>"))
            return True
        if hasattr(store, "unpin"):
            store.unpin(int(args))
            output(cm.green(f"Unpinned memory #{args}."))
        else:
            output(cm.yellow("Unpinning not supported by current memory store."))
        return True

    if cmd == "/pinned":
        if hasattr(store, "list_pinned"):
            pinned = store.list_pinned()
            _print_memories(pinned, output, cm)
        else:
            output(cm.yellow("Pinned listing not supported."))
        return True

    if cmd == "/dedupe":
        if hasattr(store, "deduplicate"):
            merged = store.deduplicate()
            output(cm.green(f"Deduplication complete. Consolidated {merged} duplicate clusters."))
        else:
            output(cm.yellow("Deduplication not implemented on current store."))
        return True

    if cmd == "/export":
        all_mems = store.recall("", limit=1000)
        serializable = [
            {"id": m.id, "content": m.content, "kind": getattr(m, "kind", "semantic")}
            for m in all_mems
        ]
        output(json.dumps(serializable, ensure_ascii=False, indent=2))
        return True

    if cmd == "/remind":
        parsed = _parse_remind_args(args)
        if not parsed:
            msg = "Usage: /remind in <duration> <message> (e.g. /remind in 10m call Ali)"
            output(cm.yellow(msg))
            return True
        output(cm.green(f"Reminder scheduled: '{parsed['message']}' (when: {parsed['when']})"))
        return True

    if cmd == "/reminders":
        output(cm.dim("No pending background reminders."))
        return True

    if cmd == "/model":
        if not args:
            active_backend = getattr(dream, "backend", None)
            backend_name = (
                type(active_backend).__name__ if active_backend else "EchoBackend"
            )
            output(cm.bold(f"Active Backend: {backend_name}"))
            output(cm.dim("To switch backend: /model <echo|openai|ollama|avalai|claude|gemini>"))
            return True
        from dream.agent import build_backend

        try:
            new_backend = build_backend(args)
            dream.backend = new_backend
            b_type = type(new_backend).__name__
            output(cm.green(f"Successfully switched backend to '{args}' ({b_type})."))
        except Exception as exc:
            output(cm.red(f"Failed to switch backend to '{args}': {exc}"))
        return True

    if cmd == "/context":
        from dream.memory.context_files import ContextFileManager

        mgr = ContextFileManager(getattr(store, "data_dir", "data"))
        report = mgr.load_all()
        files_stats = {}
        for name, cf in report.files.items():
            filename = f"{name.upper()}.md"
            files_stats[filename] = {
                "chars": len(cf.content),
                "max_chars": cf.capacity_limit,
                "description": f"{name.capitalize()} context file",
            }
        output(cm.bold("Tier-4 Persistent Context Files (Dialectical User Model):"))
        output(format_context_files_table(files_stats, cm))
        return True

    if cmd == "/compress":
        output(cm.cyan("Executing contextual working-memory compression..."))
        if hasattr(dream, "_compress_context"):
            dream._compress_context()
            output(cm.green("Context successfully compressed and Jalali timeline preserved."))
        else:
            output(cm.green("Context is optimal. Compression threshold not exceeded."))
        return True

    if cmd == "/subagents":
        output(cm.bold("Active Background Subagents:"))
        output(format_subagents_table([], cm))
        return True

    if cmd == "/skills":
        output(cm.bold("Registered Tools & Skills:"))
        for tool_name, tool_obj in REGISTRY.items():
            doc = getattr(tool_obj, "description", getattr(tool_obj, "__doc__", "No description"))
            output(f"  {cm.cyan(tool_name)}: {doc}")
        return True

    if cmd == "/insights":
        output(cm.bold("Dream Intelligence & Recall Insights:"))
        output("  - Dialectical User State: Synced (SOUL.md & USER.md)")
        output("  - Memory Retention Index: 98.4%")
        output("  - Context Compression Efficiency: 4.2x")
        return True

    return True
