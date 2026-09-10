"""Command-line argument parser construction."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser for Dream."""
    parser = argparse.ArgumentParser(description="Dream interactive assistant v2.0")
    parser.add_argument(
        "--backend",
        choices=("echo", "openai", "ollama", "avalai", "claude", "gemini"),
        default="echo",
        help="Model provider backend to use",
    )
    parser.add_argument("--owner", default="", help="Optional owner name for the session")
    parser.add_argument("--db", default="data/dream.db", help="SQLite database path")
    parser.add_argument(
        "--bridge",
        action="store_true",
        help="Start the JSON-RPC sidecar (stdin/stdout) instead of the interactive CLI",
    )
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
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Show the active plan, currency, and price, then exit",
    )
    parser.add_argument(
        "--usage",
        action="store_true",
        help="Show ledger usage for the active plan, then exit",
    )
    parser.add_argument(
        "--route",
        action="store_true",
        help="Show the active model route and whether data leaves the machine, then exit",
    )
    parser.add_argument(
        "--council",
        metavar="TOPIC",
        help="Run an offline echo council (proposer → critic → judge) on TOPIC and exit",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        default=True,
        help="Launch full interactive TUI mode with status banners",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color styling in terminal output",
    )
    return parser
