"""Interactive slash command handler for Plugin Management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.plugins.tools import get_global_plugin_manager
from dream.plugins.types import PluginStatus


def handle_plugin_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/plugin` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    mgr = get_global_plugin_manager()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "ls"):
        plugins = mgr.list_plugins()
        title = (
            "\U0001f9e9 "
            "\u0641\u0647\u0631\u0633\u062a "
            "\u0627\u0641\u0632\u0648\u0646\u0647\u200c\u0647\u0627 "
            "(Plugins):"
        )
        output(cm.bold(title))
        if not plugins:
            empty_msg = (
                "  \u2022 \u0647\u06cc\u0686 "
                "\u0627\u0641\u0632\u0648\u0646\u0647\u200c\u0627\u06cc "
                "\u0646\u0635\u0628 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
            )
            output(cm.dim(empty_msg))
            return True

        for p in plugins:
            st_color = cm.green if p.status == PluginStatus.ACTIVE else cm.red
            st_text = (
                "\u0641\u0639\u0627\u0644"
                if p.status == PluginStatus.ACTIVE
                else "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644"
            )
            output(
                f"  \u2022 {cm.bold(p.plugin_id)} (v{p.version}) - "
                f"[{st_color(st_text)}]: {p.description or p.name}"
            )
        return True

    if subcmd in ("enable", "on"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0634\u0646\u0627\u0633\u0647 "
                "\u0627\u0641\u0632\u0648\u0646\u0647 "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        p_id = parts[2]
        if mgr.enable_plugin(p_id):
            succ = (
                f"\u2713 \u0627\u0641\u0632\u0648\u0646\u0647 '{p_id}' "
                "\u0641\u0639\u0627\u0644 \u0634\u062f."
            )
            output(cm.green(succ))
        else:
            not_found = (
                f"\u2717 \u0627\u0641\u0632\u0648\u0646\u0647 '{p_id}' "
                "\u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
            )
            output(cm.red(not_found))
        return True

    if subcmd in ("disable", "off"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0634\u0646\u0627\u0633\u0647 "
                "\u0627\u0641\u0632\u0648\u0646\u0647 "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        p_id = parts[2]
        if mgr.disable_plugin(p_id):
            succ = (
                f"\u2713 \u0627\u0641\u0632\u0648\u0646\u0647 '{p_id}' "
                "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0634\u062f."
            )
            output(cm.green(succ))
        else:
            not_found = (
                f"\u2717 \u0627\u0641\u0632\u0648\u0646\u0647 '{p_id}' "
                "\u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
            )
            output(cm.red(not_found))
        return True

    if subcmd in ("info", "view"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0634\u0646\u0627\u0633\u0647 "
                "\u0627\u0641\u0632\u0648\u0646\u0647 "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        p_id = parts[2]
        plugin = mgr.get_plugin(p_id)
        if not plugin:
            not_found = (
                f"\u2717 \u0627\u0641\u0632\u0648\u0646\u0647 '{p_id}' "
                "\u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
            )
            output(cm.red(not_found))
            return True

        output(cm.bold(f"\U0001f9e9 \u0627\u0637\u0644\u0627\u0639\u0627\u062a {plugin.name}:"))
        output(f"  \u2022 \u0634\u0646\u0627\u0633\u0647: {plugin.plugin_id}")
        output(f"  \u2022 \u0646\u0633\u062e\u0647: {plugin.version}")
        output(f"  \u2022 \u062a\u0648\u0636\u06cc\u062d\u0627\u062a: {plugin.description}")
        output(f"  \u2022 \u0646\u0648\u06cc\u0633\u0646\u062f\u0647: {plugin.author}")
        perms_str = ", ".join(p.value for p in plugin.permissions) or "None"
        output(f"  \u2022 \u0645\u062c\u0648\u0632\u0647\u0627: {perms_str}")
        return True

    # Help
    h_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /plugin:"
    )
    output(cm.bold(h_title))
    output(
        "  /plugin list                        - "
        "\u0641\u0647\u0631\u0633\u062a / List plugins"
    )
    output(
        "  /plugin enable <id>                 - "
        "\u0641\u0639\u0627\u0644\u200c\u0633\u0627\u0632\u06cc / Enable plugin"
    )
    output(
        "  /plugin disable <id>                - "
        "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644\u200c\u0633\u0627\u0632\u06cc / Disable plugin"
    )
    output(
        "  /plugin info <id>                   - "
        "\u062c\u0632\u0626\u06cc\u0627\u062a \u0627\u0641\u0632\u0648\u0646\u0647 / Plugin details"
    )
    return True
