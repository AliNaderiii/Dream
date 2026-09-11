"""Interactive slash command handler for Dialectic Memory & Knowledge Graph."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.dialectic.tools import get_global_dialectic_engine


def handle_dialectic_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/dialectic` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    engine = get_global_dialectic_engine()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "info"):
        snapshot = engine.get_snapshot()
        title = (
            "\U0001f9e0 "
            "\u0648\u0636\u0639\u06cc\u062a "
            "\u062d\u0627\u0641\u0638\u0647 "
            "\u062f\u06cc\u0624\u0644\u06a9\u062a\u06cc\u06a9 "
            "(Dialectic Memory):"
        )
        output(cm.bold(title))
        n_lbl = "\u062a\u0639\u062f\u0627\u062f \u0628\u0627\u0648\u0631\u0647\u0627"
        output(f"  \u2022 {n_lbl}: {snapshot.nodes_count}")
        t_lbl = "\u062a\u0639\u062f\u0627\u062f \u062a\u0646\u0627\u0642\u0636\u0627\u062a"
        output(f"  \u2022 {t_lbl}: {snapshot.tensions_count}")
        u_lbl = (
            "\u062a\u0646\u0627\u0642\u0636\u0627\u062a "
            "\u062d\u0644\u200c\u0646\u0634\u062f\u0647"
        )
        output(f"  \u2022 {u_lbl}: {snapshot.unresolved_tensions}")

        if snapshot.top_beliefs:
            top_lbl = "\u0628\u0631\u062a\u0631\u06cc\u0646 \u0628\u0627\u0648\u0631\u0647\u0627:"
            output(f"\n  {cm.cyan(top_lbl)}")
            for b in snapshot.top_beliefs[:5]:
                stmt = b.get("statement", "")
                conf = b.get("confidence", 0.0)
                output(f"    - {stmt} (conf: {conf:.2f})")
        return True

    if subcmd in ("reflect", "synthesize"):
        snapshot = engine.reflect_and_synthesize()
        succ_msg = (
            "\u2713 \u0628\u0627\u0632\u062a\u0627\u0628 "
            "\u0648 \u0633\u0646\u062a\u0632 "
            "\u062f\u06cc\u0624\u0644\u06a9\u062a\u06cc\u06a9 "
            "\u0627\u0646\u062c\u0627\u0645 \u0634\u062f."
        )
        output(cm.green(succ_msg))
        output(f"\n{cm.dim(snapshot.synthesized_summary)}")
        return True

    if subcmd in ("observe", "add"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0645\u062a\u0646 \u0628\u0627\u0648\u0631 "
                "\u06cc\u0627 \u062a\u0631\u062c\u06cc\u062d "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        text = " ".join(parts[2:])
        node = engine.observe_statement(statement=text)
        succ = (
            f"\u2713 \u0628\u0627\u0648\u0631 '{node.statement}' "
            "\u062b\u0628\u062a \u0634\u062f."
        )
        output(cm.green(succ))
        return True

    if subcmd in ("reset", "clear"):
        engine.reset()
        rst_msg = (
            "\u2713 \u06af\u0631\u0627\u0641 "
            "\u062d\u0627\u0641\u0638\u0647 "
            "\u062f\u06cc\u0624\u0644\u06a9\u062a\u06cc\u06a9 "
            "\u067e\u0627\u06a9\u0633\u0627\u0631\u06cc "
            "\u0634\u062f."
        )
        output(cm.green(rst_msg))
        return True

    # Help
    h_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /dialectic:"
    )
    output(cm.bold(h_title))
    output(
        "  /dialectic status                   - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0648\u0636\u0639\u06cc\u062a / Dialectic status"
    )
    output(
        "  /dialectic observe <text>           - "
        "\u062b\u0628\u062a \u0628\u0627\u0648\u0631 / Observe belief"
    )
    output(
        "  /dialectic reflect                  - "
        "\u0628\u0627\u0632\u062a\u0627\u0628 \u0648 \u0633\u0646\u062a\u0632 / Reflect"
    )
    output(
        "  /dialectic reset                    - "
        "\u067e\u0627\u06a9\u0633\u0627\u0631\u06cc / Reset memory"
    )
    return True
