"""Offline-first diagnostics for a Dream installation."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable

from dream.agent import ApprovalPolicy, build_backend
from dream.memory import MemoryStore, normalize_fa
from dream.tools import REGISTRY, openai_schemas


def _report(name: str, passed: bool, detail: str, output: Callable[[str], None]) -> bool:
    output(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")
    return passed


def _mask(value: str) -> str:
    """Return a recognisable but safe representation of a secret."""
    if not value:
        return "not configured"
    return "***" if len(value) < 8 else f"{value[:3]}…{value[-2:]}"


def run_checks(backend: str | None = None, output: Callable[[str], None] = print) -> bool:
    """Run offline checks and optionally verify real model tool calling."""
    checks: list[bool] = []
    checks.append(
        _report("Python", sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", output)
    )
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE VIRTUAL TABLE check_fts USING fts5(content)")
        connection.close()
        checks.append(_report("SQLite FTS5", True, "available", output))
    except sqlite3.Error:
        checks.append(
            _report("SQLite FTS5", False, "unavailable; install SQLite with FTS5 enabled", output)
        )
    try:
        with tempfile.TemporaryDirectory() as directory:
            with MemoryStore(f"{directory}/doctor.db") as store:
                written = store.remember("doctor round trip")
                read = store.get(written.id)
                ok = read is not None and read.content == "doctor round trip"
        checks.append(
            _report(
                "Package and memory",
                ok,
                "memory round-trip succeeded" if ok else "memory round-trip failed",
                output,
            )
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        checks.append(
            _report("Package and memory", False, f"{exc}; check database permissions", output)
        )
    normalized = normalize_fa("مي‌خواهم كتاب") == normalize_fa("می‌خواهم کتاب")
    checks.append(
        _report(
            "Normalisation",
            normalized,
            "Arabic and Persian forms agree" if normalized else "normalisation mismatch",
            output,
        )
    )
    registry_ok = bool(REGISTRY)
    checks.append(
        _report(
            "Tool registry",
            registry_ok,
            "tools registered" if registry_ok else "empty; reinstall Dream",
            output,
        )
    )
    blocked, reason = ApprovalPolicy().allows("run_shell", {"command": "echo doctor"})
    checks.append(
        _report(
            "Approval gate",
            not blocked,
            reason if not blocked else "dangerous tool was allowed; remove unsafe policy",
            output,
        )
    )

    if backend:
        checks.append(_live_tool_check(backend, output))
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        output(f"API key configured: {_mask(key)}")
    return all(checks)


def _live_tool_check(backend_name: str, output: Callable[[str], None]) -> bool:
    """Ask a configured provider for a tool call, not merely fluent text."""
    try:
        backend = build_backend(backend_name)
        response = backend.chat(
            [
                {
                    "role": "user",
                    "content": "Use the calculate tool to compute 2 + 2. Do not answer in text.",
                }
            ],
            tools=openai_schemas(),
        )
        calls = response.get("tool_calls", [])
        if calls:
            return _report(
                "Live tool calling", True, f"model requested {calls[0].get('name')}", output
            )
        detail = response.get("content", "no response")
        return _report(
            "Live tool calling",
            False,
            f"model did not invoke a tool ({detail}). Choose a tool-calling model "
            "or check --backend configuration.",
            output,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _report(
            "Live tool calling", False, f"{exc}; verify backend URL, model, and API key.", output
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether Dream is ready to run")
    parser.add_argument(
        "--backend", choices=("openai", "ollama"), help="Also test a live model's tool calling"
    )
    args = parser.parse_args(argv)
    try:
        passed = run_checks(args.backend)
    except Exception as exc:  # Diagnostics must name recovery, not show a traceback.
        print(f"FAIL doctor: {exc}. Reinstall Dream and run doctor again.", file=sys.stderr)
        return 1
    if not passed:
        print(
            "One or more checks failed. Follow the action named above, then rerun doctor.",
            file=sys.stderr,
        )
        return 1
    print("Dream is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
