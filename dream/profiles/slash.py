"""Interactive slash command handler for Multi-Profile and Persona management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.profiles.tools import get_global_profile_manager


def handle_profile_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/profile` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    mgr = get_global_profile_manager()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "ls"):
        profiles = mgr.list_profiles()
        active = mgr.get_active_profile()
        title = (
            "\U0001f464 "
            "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644\u200c\u0647\u0627\u06cc "
            "\u0641\u0639\u0627\u0644 "
            f"({len(profiles)} \u0645\u0648\u0631\u062f):"
        )
        output(cm.bold(title))
        for p in profiles:
            is_active = p.name == active.name
            marker = cm.green("\u2713 ") if is_active else "  "
            active_badge = cm.green(" [\u0641\u0639\u0627\u0644]") if is_active else ""
            disp = p.display_name or p.name
            output(f"{marker}\u2022 {cm.cyan(p.name):<12} ({disp}){active_badge}")
            if p.persona_prompt:
                preview = (
                    p.persona_prompt[:50] + "..."
                    if len(p.persona_prompt) > 50
                    else p.persona_prompt
                )
                output(f"    {cm.dim(preview)}")
        return True

    if subcmd in ("switch", "use", "set"):
        if len(parts) < 3:
            msg = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0646\u0627\u0645 "
                "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u0631\u0627 "
                "\u0645\u0634\u062e\u0635 "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(msg))
            return True
        target_name = parts[2]
        prof = mgr.switch_profile(target_name)
        succ = (
            f"\u2713 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
            f"\u0641\u0639\u0627\u0644 \u0628\u0647 '{prof.name}' "
            f"({prof.display_name}) "
            "\u062a\u063a\u06cc\u06cc\u0631 "
            "\u06cc\u0627\u0641\u062a."
        )
        output(cm.green(succ))
        return True

    if subcmd in ("info", "current", "show"):
        active = mgr.get_active_profile()
        info_title = (
            "\U0001f464 "
            "\u0627\u0637\u0644\u0627\u0639\u0627\u062a "
            "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
            f"\u0641\u0639\u0627\u0644 ({active.name}):"
        )
        output(cm.bold(info_title))
        disp_name = cm.cyan(active.display_name)
        output(f"  \u2022 \u0646\u0627\u0645 \u0646\u0645\u0627\u06cc\u0634\u06cc: {disp_name}")
        model_lbl = "\u0645\u062f\u0644 \u067e\u06cc\u0634\u200c\u0641\u0631\u0636"
        output(f"  \u2022 {model_lbl}: {active.default_model}")
        output(f"  \u2022 \u0632\u0628\u0627\u0646: {active.language}")
        output(f"  \u2022 \u067e\u0631\u0633\u0648\u0646\u0627: {cm.dim(active.persona_prompt)}")
        toolsets_str = ", ".join(active.allowed_toolsets)
        output(
            f"  \u2022 \u0627\u0628\u0632\u0627\u0631\u0647\u0627\u06cc "
            f"\u0645\u062c\u0627\u0632: {toolsets_str}"
        )
        return True

    if subcmd == "create":
        if len(parts) < 3:
            msg = (
                "\u2717 \u0646\u0627\u0645 "
                "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u0644\u0627\u0632\u0645 \u0627\u0633\u062a. "
                "\u0645\u062b\u0627\u0644: /profile create coding"
            )
            output(cm.red(msg))
            return True
        name = parts[2]
        persona = " ".join(parts[3:]) if len(parts) > 3 else ""
        prof = mgr.create_profile(name=name, persona_prompt=persona)
        created_msg = (
            f"\u2713 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
            f"'{prof.name}' "
            "\u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a "
            "\u0627\u06cc\u062c\u0627\u062f "
            "\u0634\u062f."
        )
        output(cm.green(created_msg))
        return True

    if subcmd in ("delete", "rm"):
        if len(parts) < 3:
            msg = (
                "\u2717 \u0646\u0627\u0645 "
                "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u0631\u0627 \u0648\u0627\u0631\u062f "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(msg))
            return True
        target_name = parts[2]
        if mgr.delete_profile(target_name):
            succ_del = (
                f"\u2713 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                f"'{target_name}' \u062d\u0630\u0641 \u0634\u062f."
            )
            output(cm.green(succ_del))
        else:
            del_err = (
                f"\u2717 \u062d\u0630\u0641 "
                f"\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                f"'{target_name}' "
                "\u0627\u0645\u06a9\u0627\u0646\u200c\u067e\u0630\u06cc\u0631 "
                "\u0646\u06cc\u0633\u062a "
                "(\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u067e\u06cc\u0634\u200c\u0641\u0631\u0636 "
                "\u06cc\u0627 \u0641\u0639\u0627\u0644 "
                "\u0642\u0627\u0628\u0644 "
                "\u062d\u0630\u0641 "
                "\u0646\u06cc\u0633\u062a)."
            )
            output(cm.red(del_err))
        return True

    # Help
    help_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /profile:"
    )
    output(cm.bold(help_title))
    output(
        "  /profile list                       - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0641\u0647\u0631\u0633\u062a "
        "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644\u200c\u0647\u0627 / List profiles"
    )
    output(
        "  /profile switch <name>              - "
        "\u062a\u063a\u06cc\u06cc\u0631 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
        "\u0641\u0639\u0627\u0644 / Switch profile"
    )
    output(
        "  /profile create <name> [persona]    - "
        "\u0627\u06cc\u062c\u0627\u062f \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
        "\u062c\u062f\u06cc\u062f / Create profile"
    )
    output(
        "  /profile info                       - "
        "\u0646\u0645\u0627\u06cc\u0634 \u062c\u0632\u0626\u06cc\u0627\u062a "
        "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 \u0641\u0639\u0627\u0644 / Profile details"
    )
    output(
        "  /profile delete <name>              - "
        "\u062d\u0630\u0641 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 / Delete profile"
    )
    return True
