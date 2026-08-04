"""Interactive command-line interface for Dream."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

from dream.agent import ApprovalPolicy, Dream, EchoBackend, Turn
from dream.memory import MemoryStore, normalize_fa
from dream.tools import REGISTRY

KNOWN_COMMANDS = (
    "/mem",
    "/mems",
    "/stats",
    "/forget",
    "/pin",
    "/tools",
    "/reset",
    "/help",
    "/exit",
)


def _style(text: str, code: str, stream: TextIO) -> str:
    """Colour text only when it will be read in an interactive terminal."""
    return f"\x1b[{code}m{text}\x1b[0m" if stream.isatty() else text


def _closest_command(command: str) -> str | None:
    """Return the closest known command, or ``None`` when nothing is close."""
    matches = difflib.get_close_matches(command, KNOWN_COMMANDS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _print_memories(store: MemoryStore, output: Callable[[str], None]) -> None:
    memories = store.all()
    if not memories:
        output("No stored memories. Use the conversation to add one.")
        return
    for memory in memories:
        output(
            f"{memory.id}  {memory.kind:<10} importance={memory.importance:.2f}  {memory.content}"
        )


# --------------------------------------------------------------------------
# Tool-activity reporting
#
# A model can claim «ذخیره شد» without ever calling remember_fact, or call it
# and misread a failure as success. Turn already records every call's name,
# arguments, and result; printing them to stderr is what makes the CLI honest.
# --------------------------------------------------------------------------

_ARGUMENT_LIMIT = 80
_DETAIL_LIMIT = 120


def _truncate(text: str, limit: int) -> str:
    """Clip text to ``limit`` characters, marking what was dropped."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _stderr_line(line: str) -> None:
    print(line, file=sys.stderr)


def _call_status(result: str) -> tuple[str, str]:
    """Classify a recorded tool result as ok, error, or blocked."""
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return "error", "unparseable tool result"
    if not isinstance(payload, dict):
        return "ok", ""
    if payload.get("blocked"):
        return "blocked", str(payload.get("reason") or "")
    if payload.get("status") == "error" or "error" in payload:
        error = payload.get("error")
        if isinstance(error, dict):
            return "error", str(error.get("message") or error.get("type") or "")
        return "error", "" if error is None else str(error)
    return "ok", ""


def format_tool_line(name: str, arguments: dict[str, Any], result: str) -> str:
    """Render one recorded tool call as a compact one-line status."""
    rendered = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    status, detail = _call_status(result)
    line = f"[tool] {name}({_truncate(rendered, _ARGUMENT_LIMIT)}) -> {status}"
    if detail:
        line += f": {_truncate(detail, _DETAIL_LIMIT)}"
    return line


def format_extraction_line(result: Any) -> str:
    """Render one compact status line for the extraction pass."""
    status = getattr(result, "status", "")
    if status == "facts_found":
        count = len(getattr(result, "facts", []))
        return f"[extraction] facts found: {count} fact{'s' if count != 1 else ''}"
    if status == "no_facts":
        return "[extraction] no durable facts"
    if status == "too_short":
        return "[extraction] skipped as too short"
    if status == "disabled":
        return "[extraction] disabled by environment"
    if status == "unparseable":
        return "[extraction] model output unparseable"
    if status == "error":
        detail = getattr(result, "raw_text", "")
        if detail:
            return f"[extraction] backend errored: {_truncate(str(detail), _DETAIL_LIMIT)}"
        return "[extraction] backend errored"
    return f"[extraction] {status}"


def report_turn_activity(turn: Turn, output: Callable[[str], None] | None = None) -> None:
    """Print compact activity lines for tools, extraction, and stored memories.

    Defaults to stderr so the lines never pollute piped stdout output.
    """
    if output is None:
        output = _stderr_line
    for call in turn.tool_calls:
        output(
            format_tool_line(
                str(call.get("name", "")),
                call.get("arguments") or {},
                str(call.get("result", "")),
            )
        )
    injected = getattr(turn, "memories_injected", None)
    if injected is not None and len(injected) < len(turn.memories_used):
        output(
            f"[memory] recalled {len(turn.memories_used)}, injected {len(injected)} (block limit)"
        )
    if getattr(turn, "extraction", None) is not None:
        output(format_extraction_line(turn.extraction))
    if turn.memories_created:
        count = len(turn.memories_created)
        output(f"[memory] stored {count} fact{'s' if count != 1 else ''}")
    for memory in getattr(turn, "memories_superseded", []):
        output(f"[memory] superseded #{memory.id} ({memory.content})")
    for error in getattr(turn, "memory_errors", []):
        output(f"[memory] store failed: {_truncate(error, _DETAIL_LIMIT)}")


def dispatch_command(text: str, dream: Dream, output: Callable[[str], None] = print) -> bool:
    """Dispatch one slash command. Return ``False`` when the session should end.

    A leading backslash is accepted as an alias for a leading slash, so
    Windows habits like ``\\mems`` and ``\\exit`` work too.
    """
    command, _, argument = text.partition(" ")
    argument = argument.strip()
    if command.startswith("\\"):
        command = "/" + command[1:]
    store = dream.store
    if command == "/mem":
        if not argument:
            output("Usage: /mem QUERY — provide words to search for.")
        else:
            hits = store.recall(argument, reinforce=False)
            if not hits:
                output("No matching memories found.")
            for memory in hits:
                output(f"[{memory.score:.3f}] {memory.id} {memory.kind}: {memory.content}")
    elif command == "/mems":
        _print_memories(store, output)
    elif command == "/stats":
        output(json.dumps(store.stats(), ensure_ascii=False, sort_keys=True))
    elif command == "/forget":
        try:
            memory_id = int(argument)
        except ValueError:
            output("Usage: /forget ID — ID must be a number.")
        else:
            output(
                "Memory archived." if store.forget(memory_id) else "No active memory has that ID."
            )
    elif command == "/pin":
        try:
            memory_id = int(argument)
        except ValueError:
            output("Usage: /pin ID — ID must be a number.")
        else:
            output("Memory pinned." if store.pin(memory_id) else "No active memory has that ID.")
    elif command == "/tools":
        for name, registered in sorted(REGISTRY.items()):
            output(f"{name}: {registered.risk}")
    elif command == "/reset":
        dream.reset_session()
        output("Session context cleared; long-term memories remain.")
    elif command == "/help":
        output("/mem QUERY  /mems  /stats  /forget ID  /pin ID  /tools  /reset  /help  /exit")
    elif command == "/exit":
        return False
    else:
        suggestion = _closest_command(command)
        hint = f" Did you mean {suggestion}?" if suggestion else ""
        output(f"Unknown command: {command}.{hint} Type /help to see available commands.")
    return True


def run_demo(db_path: str = ":memory:", output: Callable[[str], None] = print) -> None:
    """Run an offline, deterministic tour of Dream's core capabilities."""
    with MemoryStore(db_path) as store:
        dream = Dream(store, EchoBackend())
        output("1. Seeding memories across semantic, episodic, and procedural kinds")
        store.remember("I prefer dark coffee", kind="semantic", tags=["coffee"])
        store.remember("Visited Tehran coffee shop today", kind="episodic", tags=["coffee"])
        store.remember(
            "Answer Persian questions in Persian first", kind="procedural", tags=["language"]
        )
        output("2. Hybrid retrieval for 'coffee':")
        for memory in store.recall("coffee"):
            output(f"   relevance={memory.score:.3f}  {memory.content}")
        arabic = "مي‌خواهم كتاب"
        persian = "می‌خواهم کتاب"
        output("3. Normalisation:")
        output(f"   Arabic forms  → {normalize_fa(arabic)}")
        output(f"   Persian forms → {normalize_fa(persian)}")
        output("   This matters because equivalent spellings retrieve the same stored memory.")
        output("4. Agent tool loop:")
        for question in ("What time is it?", "What is 12 × 3?"):
            turn = dream.run(question)
            output(f"   {question} {turn.reply}")

        class DangerousDemoBackend:
            def chat(self, messages, tools=None):
                if messages[-1]["role"] == "tool":
                    return {"content": "The dangerous command was refused.", "tool_calls": []}
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "demo-shell",
                            "name": "run_shell",
                            "arguments": {"command": "echo should-not-run"},
                        }
                    ],
                }

        output("5. Approval gate:")
        dangerous = Dream(store, DangerousDemoBackend(), ApprovalPolicy())
        turn = dangerous.run("Run a shell command")
        output(f"   {turn.tool_calls[0]['result']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dream interactive assistant")
    parser.add_argument("--backend", choices=("echo", "openai", "ollama"), default="echo")
    parser.add_argument("--owner", default="", help="Optional owner name for the session")
    parser.add_argument("--db", default="data/dream.db", help="SQLite database path")
    parser.add_argument(
        "--demo", action="store_true", help="Run the offline demonstration and exit"
    )
    parser.add_argument("--memories", action="store_true", help="List memories at startup")
    parser.add_argument(
        "--yolo", action="store_true", help="Allow dangerous tools without prompting"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the [tool]/[memory] activity lines on stderr",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        run_demo(args.db)
        return 0
    policy = ApprovalPolicy()
    if args.yolo:
        policy.auto_approve.add("dangerous")
        policy.always_ask.discard("dangerous")
        print(_style("WARNING: --yolo auto-approves dangerous tools.", "31;1", sys.stdout))
    from dream.agent import build_backend

    try:
        with MemoryStore(args.db) as store:
            dream = Dream(store, build_backend(args.backend), policy)
            if args.memories:
                _print_memories(store, print)
            owner = f", {args.owner}" if args.owner else ""
            print(_style(f"Dream is ready{owner}. Type /help for commands.", "36", sys.stdout))
            while True:
                try:
                    text = input("> ")
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye.")
                    break
                if not text.strip():
                    continue
                if text.startswith(("/", "\\")):
                    if not dispatch_command(text, dream):
                        break
                    continue
                turn = dream.run(text)
                if not args.quiet:
                    report_turn_activity(turn)
                print(turn.reply)
    except OSError as exc:
        print(
            f"Could not open Dream database: {exc}. Try --db PATH with a writable location.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
