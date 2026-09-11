"""Interactive slash command handler for Agent Client Protocol (ACP)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.acp.tools import get_global_acp_manager, get_global_acp_server


def handle_acp_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/acp` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    server = get_global_acp_server()
    mgr = get_global_acp_manager()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "info"):
        agents = mgr.list_agents()
        title = (
            "\U0001f5a5\ufe0f "
            "\u0648\u0636\u0639\u06cc\u062a "
            "\u067e\u0631\u0648\u062a\u06a9\u0644 "
            "ACP:"
        )
        output(cm.bold(title))
        s_cnt = len(server._sessions)
        s_lbl = "\u0646\u0634\u0633\u062a\u200c\u0647\u0627"
        output(f"  \u2022 {s_lbl}: {s_cnt}")
        a_cnt = len(agents)
        a_lbl = "\u0627\u06cc\u062c\u0646\u062a\u200c\u0647\u0627"
        output(f"  \u2022 {a_lbl}: {a_cnt}")

        if agents:
            ag_hdr = "\u0641\u0647\u0631\u0633\u062a:"
            output(f"\n  {cm.cyan(ag_hdr)}")
            for a in agents:
                st = (
                    cm.green("\u0641\u0639\u0627\u0644")
                    if a.get("enabled")
                    else cm.red("\u063a\u06cc\u0631\u0641\u0639\u0627\u0644")
                )
                output(f"    - {cm.bold(a['id'])} ({a['name']}) [{st}]: {a.get('endpoint')}")
        return True

    if subcmd in ("agents", "list"):
        agents = mgr.list_agents()
        title = (
            "\U0001f916 "
            "\u0627\u06cc\u062c\u0646\u062a\u200c\u0647\u0627\u06cc "
            "ACP:"
        )
        output(cm.bold(title))
        for a in agents:
            output(f"  \u2022 {cm.bold(a['id'])}: {a['name']} ({a['endpoint']})")
        return True

    if subcmd in ("sessions",):
        s_title = (
            "\U0001f4c2 "
            "\u0646\u0634\u0633\u062a\u200c\u0647\u0627\u06cc "
            "ACP:"
        )
        output(cm.bold(s_title))
        if not server._sessions:
            no_sess = (
                "  \u2022 \u0647\u06cc\u0686 "
                "\u0646\u0634\u0633\u062a\u06cc "
                "\u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
            )
            output(cm.dim(no_sess))
            return True
        for s in server._sessions.values():
            output(f"  \u2022 {cm.bold(s.id)} - {s.title} ({len(s.messages)} msgs)")
        return True

    # Help
    h_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /acp:"
    )
    output(cm.bold(h_title))
    output(
        "  /acp status                         - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0648\u0636\u0639\u06cc\u062a / ACP status"
    )
    output(
        "  /acp agents                         - "
        "\u0644\u06cc\u0633\u062a \u0627\u06cc\u062c\u0646\u062a\u200c\u0647\u0627 / List agents"
    )
    output(
        "  /acp sessions                       - "
        "\u0646\u0634\u0633\u062a\u200c\u0647\u0627 / Sessions"
    )
    return True
