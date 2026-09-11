"""Slash command handler for plugin management."""

from __future__ import annotations

from collections.abc import Callable

from dream.plugins.tools import get_plugin_manager


def handle_plugin_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/plugins` or `/plugin` slash commands.

    Usage:
        /plugins
        /plugin list
        /plugin enable <name>
        /plugin disable <name>
        /plugin info <name>
    """
    parts = args.strip().split()
    mgr = get_plugin_manager()

    if not parts or parts[0] in ("list", "status"):
        plugins = mgr.list_plugins()
        output("🧩 **پلاگین‌های نصب‌شده / Installed Plugins:**\n")
        for p in plugins:
            status_icon = "🟢" if p.status.value == "active" else "⚪"
            tools_count = len(p.tools_registered)
            desc = p.manifest.description_fa or p.manifest.description_en
            tools_str = ", ".join(p.tools_registered) if tools_count else "بدون ابزار"
            output(
                f"  {status_icon} **{p.manifest.name}** (v{p.manifest.version}) "
                f"— {p.status.value}\n"
                f"     {desc}\n"
                f"     ابزارها: {tools_count} ابزار ({tools_str})\n"
            )
        return True

    action = parts[0].lower()
    if action == "enable" and len(parts) > 1:
        name = parts[1]
        ok = mgr.enable_plugin(name)
        if ok:
            output(f"✅ پلاگین `{name}` فعال شد. / Plugin `{name}` enabled.")
        else:
            output(f"❌ خطا در فعال‌سازی پلاگین `{name}`. / Failed to enable.")
        return True

    if action == "disable" and len(parts) > 1:
        name = parts[1]
        ok = mgr.disable_plugin(name)
        if ok:
            output(f"⚪ پلاگین `{name}` غیرفعال شد. / Plugin `{name}` disabled.")
        else:
            output(f"❌ خطا در غیرفعال‌سازی پلاگین `{name}`.")
        return True

    if action == "info" and len(parts) > 1:
        name = parts[1]
        p = mgr.get_plugin(name)
        if not p:
            output(f"❌ پلاگین `{name}` یافت نشد.")
            return True
        output(f"ℹ️ **اطلاعات پلاگین {p.manifest.name}:**\n")
        output(f"  نسخه: {p.manifest.version}\n  نویسنده: {p.manifest.author}\n")
        output(f"  توضیحات: {p.manifest.description_fa}\n")
        tools = [t.get("name", "") for t in p.register_tools()]
        output(f"  ابزارهای ارائه‌شده: {', '.join(tools) if tools else 'هیچ'}\n")
        return True

    output(
        "راهنمای دستور پلاگین / Plugin Command Help:\n"
        "  /plugins\n"
        "  /plugin enable <name>\n"
        "  /plugin disable <name>\n"
        "  /plugin info <name>"
    )
    return True
