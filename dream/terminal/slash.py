"""Slash command handler for terminal management."""

from __future__ import annotations

from collections.abc import Callable

from dream.terminal.tools import get_terminal_manager


def handle_terminal_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/terminal` or `/backend` slash commands.

    Usage:
        /terminal
        /terminal backends
        /terminal set <local|docker|ssh|singularity|modal|daytona|vercel>
    """
    parts = args.strip().split()
    mgr = get_terminal_manager()

    if not parts or parts[0] in ("status", "backends", "list"):
        header = (
            "\U0001f5a5\ufe0f "
            "**\u067e\u0627\u06cc\u0627\u0646\u0647\u200c\u0647\u0627\u06cc "
            "\u0627\u062c\u0631\u0627\u06cc\u06cc "
            "\u0641\u0639\u0627\u0644 / Terminal Backends:**\n"
        )
        output(header)
        for b in mgr.list_backends():
            status_icon = "\U0001f7e2" if b["available"] else "\U0001f534"
            active_marker = "★ [ACTIVE]" if b["is_active"] else ""
            output(
                f"  {status_icon} **{b['type'].upper()}** {active_marker}\n"
                f"     Status: {b['details']} (Latency: {b['latency_ms']:.1f}ms)\n"
            )
        return True

    if parts[0] in ("set", "switch", "use") and len(parts) > 1:
        target = parts[1]
        ok = mgr.set_active_backend(target)
        if ok:
            succ = (
                f"\u2705 \u067e\u0627\u06cc\u0627\u0646\u0647 "
                f"\u0641\u0639\u0627\u0644 \u0628\u0647 `{target}` "
                "\u062a\u063a\u06cc\u06cc\u0631 \u06cc\u0627\u0641\u062a. / "
                f"Active terminal backend set to `{target}`."
            )
            output(succ)
        else:
            err = (
                f"\u274c \u067e\u0627\u06cc\u0627\u0646\u0647 `{target}` "
                "\u06cc\u0627\u0641\u062a \u0646\u0634\u062f "
                "\u06cc\u0627 \u062f\u0631 \u062f\u0633\u062a\u0631\u0633 "
                "\u0646\u06cc\u0633\u062a. / "
                "Backend not found or unavailable."
            )
            output(err)
        return True

    help_msg = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 \u067e\u0627\u06cc\u0627\u0646\u0647 / Terminal Help:\n"
        "  /terminal\n"
        "  /terminal set <local|docker|ssh|singularity|modal|daytona|vercel>"
    )
    output(help_msg)
    return True
