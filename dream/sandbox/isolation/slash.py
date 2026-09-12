"""CLI and slash command handlers for Sandbox Isolation and WASM Virtualization."""

from __future__ import annotations

from typing import Any

from dream.sandbox.isolation.tools import (
    sandbox_export_security_report,
    sandbox_isolate_execute,
    sandbox_reset_isolation,
    sandbox_wasm_execute,
)


def handle_isolation_slash_command(command_str: str) -> str:
    """Handle /isolate, /wasm, and /sandbox_security CLI slash commands.

    Usage:
        /isolate <code>
        /wasm <code_or_expression>
        /sandbox_security [reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/isolate"):
        code = cmd[len("/isolate") :].strip()
        if not code:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u06a9\u062f \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u062c\u0631\u0627\u06cc \u0627\u06cc\u0632\u0648\u0644\u0647 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = sandbox_isolate_execute(code)
        r = res.get("result", {})
        if not r.get("success"):
            return (
                f"\u26d4 \u0627\u062c\u0631\u0627 \u0628\u0647 \u062f\u0644\u06cc\u0644 \u0646\u0642\u0636 \u0633\u06cc\u0627\u0633\u062a \u0627\u0645\u0646\u06cc\u062a\u06cc \u0645\u0633\u062f\u0648\u062f \u0634\u062f:\n"
                f"- \u0645\u0648\u0627\u0631\u062f \u0646\u0642\u0636: {', '.join(r.get('security_violations', []))}\n"
                f"- \u0633\u06cc\u0633\u200c\u06a9\u0627\u0644\u200c\u0647\u0627: {', '.join(r.get('syscalls_blocked', []))}"
            )
        return (
            f"\U0001f6e1\ufe0f \u0627\u062c\u0631\u0627\u06cc \u0627\u06cc\u0632\u0648\u0644\u0647 \u0645\u0648\u0641\u0642 ({r.get('duration_ms'):.1f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647):\n"
            f"```\n{r.get('stdout')}\n```"
        )

    if cmd.startswith("/wasm"):
        expr = cmd[len("/wasm") :].strip()
        if not expr:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0639\u0628\u0627\u0631\u062a \u06cc\u0627 \u06a9\u062f \u0645\u062d\u0627\u0633\u0628\u0627\u062a\u06cc \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = sandbox_wasm_execute(expr)
        r = res.get("result", {})
        if not r.get("success"):
            return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0645\u062d\u0627\u0633\u0628\u0647 WASM:\n{r.get('stderr')}"
        return (
            f"\u26a1 \u0646\u062a\u06cc\u062c\u0647 \u0645\u062d\u0627\u0633\u0628\u0647 \u062f\u0631 \u0645\u0627\u06cc\u06a9\u0631\u0648\u0631\u0627\u0646\u200c\u062a\u0627\u06cc\u0645 WASM ({r.get('duration_ms'):.2f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647):\n"
            f"```\n{r.get('stdout')}\n```"
        )

    if cmd.startswith("/sandbox_security"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            sandbox_reset_isolation()
            return "\u2705 \u0622\u0645\u0627\u0631 \u0627\u06cc\u0632\u0648\u0644\u0627\u0633\u06cc\u0648\u0646 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

        res = sandbox_export_security_report()
        return res.get("markdown_report", "")

    return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
