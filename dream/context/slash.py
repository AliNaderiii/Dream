"""Interactive slash command handler for Layered Context Hierarchy management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.context.tools import get_global_context_engine


def handle_context_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/context` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    engine = get_global_context_engine()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "list", "ls"):
        report = engine.get_budget_report()
        title = (
            "\U0001f4c4 "
            "\u0648\u0636\u0639\u06cc\u062a "
            "\u0641\u0627\u06cc\u0644\u200c\u0647\u0627\u06cc "
            "\u0632\u0645\u06cc\u0646\u0647 (Context Hierarchy):"
        )
        output(cm.bold(title))
        for _tier_name, info in report["tiers"].items():
            fname = info["file"]
            act_len = info["actual_length"]
            alloc = info["allocated_budget"]
            vol_lbl = "\u062d\u062c\u0645"
            char_lbl = "\u06a9\u0627\u0631\u0627\u06a9\u062a\u0631"
            bud_lbl = "\u0628\u0648\u062f\u062c\u0647"
            output(
                f"  \u2022 {cm.cyan(fname):<14} "
                f"({vol_lbl}: {act_len} {char_lbl} / {bud_lbl}: {alloc})"
            )
        total_chars = report["total_rendered_chars"]
        est_tokens = report["estimated_tokens"]
        tot_lbl = "\u0645\u062c\u0645\u0648\u0639 \u062a\u0648\u06a9\u0646\u200c\u0647\u0627"
        output(f"  \u2022 {tot_lbl}: {cm.green(str(est_tokens))} ({total_chars} chars)")
        return True

    if subcmd in ("view", "show", "cat"):
        target_tier = parts[2].lower() if len(parts) > 2 else "soul"
        cfile = engine.get_tier(target_tier)
        hdr = (
            f"\U0001f4c4 "
            f"\u0645\u062d\u062a\u0648\u0627\u06cc "
            f"{cfile.filename} "
            f"({len(cfile.content)} \u06a9\u0627\u0631\u0627\u06a9\u062a\u0631):"
        )
        output(cm.bold(hdr))
        output(cm.dim("-" * 50))
        output(cfile.content)
        output(cm.dim("-" * 50))
        return True

    if subcmd in ("update", "edit", "set"):
        if len(parts) < 4:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0646\u0627\u0645 "
                "\u0644\u0627\u06cc\u0647 (soul/agents/user/memory) "
                "\u0648 \u0645\u062a\u0646 \u062c\u062f\u06cc\u062f "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        target_tier = parts[2].lower()
        new_content = " ".join(parts[3:])
        if engine.update_tier(target_tier, new_content):
            succ = (
                f"\u2713 \u0641\u0627\u06cc\u0644 "
                f"'{target_tier.upper()}.md' "
                "\u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a "
                "\u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc "
                "\u0634\u062f."
            )
            output(cm.green(succ))
        else:
            err_up = (
                "\u2717 \u062e\u0637\u0627 "
                "\u062f\u0631 \u0630\u062e\u06cc\u0631\u0647\u0633\u0627\u0632\u06cc."
            )
            output(cm.red(err_up))
        return True

    if subcmd in ("reload", "refresh"):
        res = engine.reload_all()
        succ_re = (
            f"\u2713 {len(res)} "
            "\u0641\u0627\u06cc\u0644 \u0632\u0645\u06cc\u0646\u0647 "
            "\u0645\u062c\u062f\u062f\u0627\u064b \u0627\u0632 "
            "\u062f\u06cc\u0633\u06a9 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc "
            "\u0634\u062f\u0646\u062f."
        )
        output(cm.green(succ_re))
        return True

    # Help
    help_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /context:"
    )
    output(cm.bold(help_title))
    output(
        "  /context status                     - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0648\u0636\u0639\u06cc\u062a \u0648 "
        "\u0628\u0648\u062f\u062c\u0647 \u062a\u0648\u06a9\u0646\u200c\u0647\u0627 / Context status"
    )
    output(
        "  /context view <tier>                - "
        "\u0645\u0634\u0627\u0647\u062f\u0647 \u0645\u062d\u062a\u0648\u0627 / View tier content"
    )
    output(
        "  /context update <tier> <text>       - "
        "\u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc / Update context file"
    )
    output(
        "  /context reload                     - "
        "\u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0645\u062c\u062f\u062f / Reload cache"
    )
    return True
