"""Main CLI and TUI execution runners."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable

from dream.agent import ApprovalPolicy, Dream, EchoBackend
from dream.memory import MemoryStore, normalize_fa
from dream.tui.colors import ColorManager, style
from dream.tui.repl import InteractiveSession


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


def run_council_cli(topic: str, output: Callable[[str], None] = print) -> int:
    """Run one echo council to completion and print its three roles + winner."""
    from dream.council import CouncilSpec, get_council, run_council
    from dream.subagents import SubAgentManager

    async def scenario() -> int:
        manager = SubAgentManager()
        result = run_council(manager, CouncilSpec(prompt=topic))
        if result.refusal is not None:
            output(f"{result.refusal}")
            return 1
        output(f"Council {result.council_id}:")
        await manager.wait_pipeline(result.pipeline_id, timeout=30.0)
        fresh = get_council(manager, result.council_id)
        if fresh is None or fresh.winner is None:
            output("Council did not finish.")
            return 1
        for member in fresh.members:
            excerpt = (member.result or "").replace("\n", " ")
            output(f"  [{member.role}] ({member.provider}) {excerpt[:200]}")
        output(f"  winner: {fresh.winner}")
        output(f"  {fresh.sentence_en}")
        output(f"  {fresh.sentence_fa}")
        return 0

    return asyncio.run(scenario())


def run_cli(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run interactive session or designated subcommand."""
    from dream.cli.args import build_parser

    args = build_parser().parse_args(argv)
    if args.demo:
        run_demo(args.db)
        return 0
    if args.plan:
        from dream.commerce import current_plan_text

        print(current_plan_text())
        return 0
    if args.usage:
        from dream.commerce import usage_text

        print(usage_text())
        return 0
    if args.route:
        from dream.router import route_text

        print(route_text())
        return 0
    if args.council:
        return run_council_cli(args.council)
    if args.bridge:
        from dream.bridge.server import run_stdio

        return run_stdio()

    policy = ApprovalPolicy()
    if args.yolo:
        policy.auto_approve.add("dangerous")
        policy.always_ask.discard("dangerous")
        print(style("WARNING: --yolo auto-approves dangerous tools.", "31;1", sys.stdout))

    from dream.agent import build_backend

    try:
        with MemoryStore(args.db) as store:
            dream = Dream(store, build_backend(args.backend), policy)
            colors = ColorManager(sys.stdout, no_color=args.no_color)
            session = InteractiveSession(
                dream=dream,
                store=store,
                owner=args.owner,
                quiet=args.quiet,
                colors=colors,
                output=print,
            )
            session.start(show_banner=True)
    except OSError as exc:
        print(
            f"Could not open Dream database: {exc}. Try --db PATH with a writable location.",
            file=sys.stderr,
        )
        return 1
    return 0
