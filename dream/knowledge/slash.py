"""Interactive slash command handler for Multimodal Temporal Knowledge Graph."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.knowledge.tools import (
    knowledge_get_entity_timeline,
    knowledge_get_stats,
    knowledge_query_temporal,
)


def handle_knowledge_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/kg` or `/knowledge` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    parts = cmd_text.strip().split(maxsplit=2)
    subcmd = parts[1].lower() if len(parts) > 1 else "stats"

    if subcmd in ("stats", "status", "info"):
        res = knowledge_get_stats()
        title = (
            "\U0001f4ca "
            "\u0622\u0645\u0627\u0631 "
            "\u06af\u0631\u0627\u0641 "
            "\u062f\u0627\u0646\u0634 \u0632\u0645\u0627\u0646\u06cc "
            "(Temporal KG):"
        )
        output(cm.bold(title))
        output(
            f"  \u2022 \u062a\u0639\u062f\u0627\u062f "
            f"\u06af\u0631\u0647\u200c\u0647\u0627 (Nodes): {res.get('total_nodes', 0)}"
        )
        output(
            f"  \u2022 \u062a\u0639\u062f\u0627\u062f "
            f"\u06cc\u0627\u0644\u200c\u0647\u0627 (Edges): {res.get('total_edges', 0)}"
        )
        output(
            f"  \u2022 \u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627\u06cc "
            f"\u0632\u0645\u0627\u0646\u06cc (Timeline Events): "
            f"{res.get('total_timeline_events', 0)}"
        )
        mod_dist = res.get("modalities_distribution", {})
        m_lbl = (
            "\u062a\u0648\u0632\u06cc\u0639 "
            "\u0645\u0648\u062f\u0627\u0644\u06cc\u062a\u0647\u0627:"
        )
        output(f"  \u2022 {m_lbl} {mod_dist}")
        return True

    if subcmd in ("query", "search", "q"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0639\u0628\u0627\u0631\u062a "
                "\u062c\u0633\u062a\u062c\u0648 \u0631\u0627 "
                "\u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        q_text = parts[2]
        res = knowledge_query_temporal(q_text)
        narrative = res.get("summary_narrative", "")
        if narrative:
            output(cm.green(narrative))
        else:
            no_match = (
                "\u2717 \u0645\u0648\u0631\u062f\u06cc "
                "\u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
            )
            output(cm.yellow(no_match))
        return True

    if subcmd in ("timeline", "events", "t"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0646\u0627\u0645 \u0645\u0648\u062c\u0648\u062f\u06cc\u062a "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        ent_name = parts[2]
        res = knowledge_get_entity_timeline(ent_name)
        events = res.get("timeline_events", [])
        cnt_ev = len(events)
        title = (
            f"\U0001f4c5 \u062a\u0627\u06cc\u0645\u200c\u0644\u0627\u06cc\u0646 "
            f"\u0632\u0645\u0627\u0646\u06cc: {ent_name} "
            f"({cnt_ev} \u0631\u0648\u06cc\u062f\u0627\u062f)"
        )
        output(cm.bold(title))
        for ev in events:
            j_date = ev.get("jalali_date") or "N/A"
            mod = ev.get("modality", "text")
            output(f"  \u2022 [{j_date}] ({mod}) {ev.get('description')}")
        return True

    # Help
    h_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /kg:"
    )
    output(cm.bold(h_title))
    output(
        "  /kg stats                           - "
        "\u0622\u0645\u0627\u0631 \u06af\u0631\u0627\u0641 \u062f\u0627\u0646\u0634 / KG Statistics"
    )
    output(
        "  /kg query <text>                    - "
        "\u062c\u0633\u062a\u062c\u0648\u06cc \u0632\u0645\u0627\u0646\u06cc / Temporal Search"
    )
    output(
        "  /kg timeline <entity>               - "
        "\u062a\u0627\u06cc\u0645\u200c\u0644\u0627\u06cc\u0646 / Entity Timeline"
    )
    return True
