"""Interactive command-line interface for Dream."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import TextIO

from dream.agent import ApprovalPolicy, Dream, EchoBackend
from dream.memory import MemoryStore, normalize_fa
from dream.tools import REGISTRY


def _style(text: str, code: str, stream: TextIO) -> str:
    """Colour text only when it will be read in an interactive terminal."""
    return f"\x1b[{code}m{text}\x1b[0m" if stream.isatty() else text


def _print_memories(store: MemoryStore, output: Callable[[str], None]) -> None:
    memories = store.all()
    if not memories:
        output("No stored memories. Use the conversation to add one.")
        return
    for memory in memories:
        output(
            f"{memory.id}  {memory.kind:<10} importance={memory.importance:.2f}  {memory.content}"
        )


def dispatch_command(text: str, dream: Dream, output: Callable[[str], None] = print) -> bool:
    """Dispatch one slash command. Return ``False`` when the session should end."""
    command, _, argument = text.partition(" ")
    argument = argument.strip()
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
    elif command == "/tools":
        for name, registered in sorted(REGISTRY.items()):
            output(f"{name}: {registered.risk}")
    elif command == "/reset":
        dream.reset_session()
        output("Session context cleared; long-term memories remain.")
    elif command == "/help":
        output("/mem QUERY  /mems  /stats  /forget ID  /tools  /reset  /help  /exit")
    elif command == "/exit":
        return False
    else:
        output(f"Unknown command: {command}. Type /help to see available commands.")
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
                if text.startswith("/"):
                    if not dispatch_command(text, dream):
                        break
                    continue
                turn = dream.run(text)
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
