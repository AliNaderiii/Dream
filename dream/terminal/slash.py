"""Slash command handler for terminal management."""

from __future__ import annotations

from collections.abc import Callable

from dream.terminal.tools import get_terminal_manager


def handle_terminal_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/terminal` or `/backend` slash commands.

    Usage:
        /terminal
        /terminal backends
        /terminal set <local|docker|ssh>
    """
    parts = args.strip().split()
    mgr = get_terminal_manager()

    if not parts or parts[0] in ("status", "backends", "list"):
        output("🖥️ **پایانه‌های اجرایی فعال / Terminal Backends:**\n")
        for b in mgr.list_backends():
            status_icon = "🟢" if b["available"] else "🔴"
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
            output(
                f"✅ پایانه فعال به `{target}` تغییر یافت. / "
                f"Active terminal backend set to `{target}`."
            )
        else:
            output(
                f"❌ پایانه `{target}` یافت نشد یا در دسترس نیست. / "
                f"Backend not found or unavailable."
            )
        return True

    output(
        "راهنمای دستور پایانه / Terminal Command Help:\n"
        "  /terminal\n"
        "  /terminal set <local|docker|ssh>"
    )
    return True
