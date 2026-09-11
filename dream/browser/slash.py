"""Interactive slash command handler for Browser Automation management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.browser.tools import get_global_browser_engine


def handle_browser_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/browser` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    engine = get_global_browser_engine()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "info"):
        status = engine.get_status()
        title = (
            "\U0001f310 "
            "\u0648\u0636\u0639\u06cc\u062a "
            "\u0645\u0631\u0648\u0631\u06af\u0631 "
            f"({status.backend.value.upper()}):"
        )
        output(cm.bold(title))
        act_status = (
            cm.green("\u0641\u0639\u0627\u0644 (Active)")
            if status.is_active
            else cm.red("\u063a\u06cc\u0631\u0641\u0639\u0627\u0644 (Closed)")
        )
        output(f"  \u2022 \u0648\u0636\u0639\u06cc\u062a \u0646\u0634\u0633\u062a: {act_status}")
        curr_url_txt = cm.cyan(status.current_url)
        output(f"  \u2022 \u0622\u062f\u0631\u0633 \u0641\u0639\u0644\u06cc: {curr_url_txt}")
        output(f"  \u2022 \u0639\u0646\u0648\u0627\u0646: {status.page_title}")
        act_cnt_lbl = "\u062a\u0639\u062f\u0627\u062f \u0627\u0642\u062f\u0627\u0645\u0627\u062a"
        output(f"  \u2022 {act_cnt_lbl}: {status.actions_count}")
        return True

    if subcmd in ("open", "goto", "navigate"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0622\u062f\u0631\u0633 URL "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        target_url = parts[2]
        load_msg = (
            f"\U0001f310 \u062f\u0631 \u062d\u0627\u0644 "
            f"\u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc '{target_url}'..."
        )
        output(cm.cyan(load_msg))
        snapshot = engine.navigate(target_url)
        succ_open = (
            f"\u2713 \u0635\u0641\u062d\u0647 '{snapshot.title}' "
            "\u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a "
            "\u0628\u0627\u0632 \u0634\u062f."
        )
        output(cm.green(succ_open))
        elem_cnt = len(snapshot.elements)
        elem_lbl = "\u062a\u0639\u062f\u0627\u062f \u0627\u0644\u0645\u0627\u0646\u200c\u0647\u0627"
        output(f"  \u2022 {elem_lbl}: {elem_cnt}")
        return True

    if subcmd in ("click",):
        if len(parts) < 3:
            err = (
                "\u2717 \u0633\u0644\u06a9\u062a\u0648\u0631 "
                "\u06cc\u0627 \u0646\u0627\u0645 "
                "\u062f\u06a9\u0645\u0647 "
                "\u0644\u0627\u0632\u0645 \u0627\u0633\u062a."
            )
            output(cm.red(err))
            return True

        selector = " ".join(parts[2:])
        engine.click(selector)
        clk_msg = (
            f"\u2713 \u06a9\u0644\u06cc\u06a9 "
            f"\u0631\u0648\u06cc '{selector}' "
            "\u0627\u0646\u062c\u0627\u0645 \u0634\u062f."
        )
        output(cm.green(clk_msg))
        return True

    if subcmd in ("type", "input"):
        if len(parts) < 4:
            err = (
                "\u2717 \u0633\u0644\u06a9\u062a\u0648\u0631 "
                "\u0648 \u0645\u062a\u0646 "
                "\u0648\u0631\u0648\u062f\u06cc "
                "\u0644\u0627\u0632\u0645 \u0627\u0633\u062a."
            )
            output(cm.red(err))
            return True

        selector = parts[2]
        text = " ".join(parts[3:])
        engine.type_text(selector, text)
        typ_msg = (
            f"\u2713 \u0645\u062a\u0646 '{text}' "
            f"\u062f\u0631 '{selector}' "
            "\u0646\u0648\u0634\u062a\u0647 \u0634\u062f."
        )
        output(cm.green(typ_msg))
        return True

    if subcmd in ("snap", "screenshot"):
        path = parts[2] if len(parts) > 2 else None
        saved_path = engine.take_screenshot(path)
        snap_lbl = "\u062a\u0635\u0648\u06cc\u0631 \u0635\u0641\u062d\u0647"
        output(cm.green(f"\U0001f4f8 {snap_lbl}: {saved_path}"))
        return True

    if subcmd in ("close", "exit", "quit"):
        engine.close()
        cls_lbl = (
            "\u0646\u0634\u0633\u062a "
            "\u0645\u0631\u0648\u0631\u06af\u0631 "
            "\u0628\u0633\u062a\u0647 "
            "\u0634\u062f."
        )
        output(cm.green(f"\u2713 {cls_lbl}"))
        return True

    # Help
    help_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /browser:"
    )
    output(cm.bold(help_title))
    output(
        "  /browser open <url>                 - "
        "\u0628\u0627\u0632 \u06a9\u0631\u062f\u0646 \u0635\u0641\u062d\u0647 / Open URL"
    )
    output(
        "  /browser click <selector>           - "
        "\u06a9\u0644\u06cc\u06a9 \u0631\u0648\u06cc \u062f\u06a9\u0645\u0647 / Click element"
    )
    output(
        "  /browser type <selector> <text>     - "
        "\u062a\u0627\u06cc\u067e \u062f\u0631 \u0641\u06cc\u0644\u062f / Type in field"
    )
    output(
        "  /browser snap [path]                - "
        "\u0627\u0633\u06a9\u0631\u06cc\u0646\u200c\u0634\u0627\u062a / Screenshot"
    )
    output(
        "  /browser status                     - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0648\u0636\u0639\u06cc\u062a / Browser status"
    )
    output(
        "  /browser close                      - "
        "\u0628\u0633\u062a\u0646 \u0645\u0631\u0648\u0631\u06af\u0631 / Close session"
    )
    return True
