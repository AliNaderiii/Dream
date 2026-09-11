"""Interactive slash command handler for Multi-Agent Swarm management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.swarm.tools import get_global_swarm_coordinator


def handle_swarm_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/swarm` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    coord = get_global_swarm_coordinator()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "info", "ls", "list"):
        summary = coord.get_status_summary()
        title = (
            "\U0001f41d "
            "\u0648\u0636\u0639\u06cc\u062a "
            "\u06a9\u0644\u0627\u0633\u062a\u0631 "
            "\u0633\u0648\u0627\u0631\u0645 "
            f"({summary['nodes_count']} \u0639\u0627\u0645\u0644 \u0641\u0639\u0627\u0644):"
        )
        output(cm.bold(title))
        leader = summary.get("leader")
        if leader:
            ldr_txt = f"{leader['name']} ({leader['role']})"
            lbl_lead = "\u0631\u0647\u0628\u0631 \u0633\u0648\u0627\u0631\u0645"
            output(f"  \u2022 {lbl_lead}: {cm.cyan(ldr_txt)}")

        mem_lbl = "\u0639\u0627\u0645\u0644\u200c\u0647\u0627\u06cc \u0639\u0636\u0648:"
        output(cm.bold(f"  {mem_lbl}"))
        for n in summary["active_nodes"]:
            role_badge = cm.yellow(f"[{n['role']}]")
            output(f"    \u2022 {n['name']:<22} {role_badge} ({n['model']})")

        prog = summary["dag_progress"]
        p_txt = f"{prog['pct']}% ({prog['completed']}/{prog['total']})"
        prog_lbl = "\u067e\u06cc\u0634\u0631\u0641\u062a \u062a\u0633\u06a9\u200c\u0647\u0627"
        output(f"  \u2022 {prog_lbl}: {cm.green(p_txt)}")
        return True

    if subcmd in ("run", "exec", "plan"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0647\u062f\u0641 \u06cc\u0627 "
                "\u0639\u0646\u0648\u0627\u0646 "
                "\u062a\u0633\u06a9 "
                "\u0631\u0627 "
                "\u0648\u0627\u0631\u062f "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        goal = " ".join(parts[2:])
        plan_msg = (
            f"\U0001f41d \u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0631\u06cc\u0632\u06cc "
            f"\u0648 \u0627\u062c\u0631\u0627\u06cc "
            f"\u0633\u0648\u0627\u0631\u0645 "
            f"\u0628\u0631\u0627\u06cc: '{goal}'..."
        )
        output(cm.cyan(plan_msg))
        tasks = coord.plan_workflow(goal)
        dag_msg = (
            f"  \u2713 {len(tasks)} "
            "\u062a\u0633\u06a9 \u062f\u0631 "
            "\u06af\u0631\u0627\u0641 DAG "
            "\u0627\u06cc\u062c\u0627\u062f "
            "\u0634\u062f."
        )
        output(cm.green(dag_msg))

        res = coord.run_all_steps()
        succ = (
            f"\u2713 \u0627\u062c\u0631\u0627 \u062f\u0631 "
            f"{res['iterations']} \u06af\u0627\u0645 \u0628\u0627 "
            "\u0645\u0648\u0641\u0642\u06cc\u062a "
            "\u06a9\u0627\u0645\u0644 \u0634\u062f."
        )
        output(cm.green(succ))
        return True

    if subcmd in ("vote", "consensus"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0645\u062a\u0646 "
                "\u067e\u06cc\u0634\u0646\u0647\u0627\u062f "
                "\u0631\u0627 "
                "\u0648\u0627\u0631\u062f "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        prop = " ".join(parts[2:])
        vote_init = (
            "\U0001f5f3\ufe0f \u062f\u0631 "
            "\u062d\u0627\u0644 \u0627\u062e\u0630 "
            "\u0622\u0631\u0627\u06cc "
            "\u0639\u0627\u0645\u0644\u200c\u0647\u0627\u06cc "
            "\u0633\u0648\u0627\u0631\u0645..."
        )
        output(cm.cyan(vote_init))
        dec = coord.vote_on_proposal(prop)
        status_color = cm.green if dec.passed else cm.red
        verdict_txt = (
            f"\u0646\u062a\u06cc\u062c\u0647 "
            f"\u0627\u062c\u0645\u0627\u0639: {dec.verdict.upper()} "
            f"(\u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {dec.confidence})"
        )
        output(status_color(f"  \u2022 {verdict_txt}"))
        if dec.reasoning:
            reasons_lbl = "\u062f\u0644\u0627\u06cc\u0644"
            output(f"  \u2022 {reasons_lbl}: {cm.dim(dec.reasoning[:80])}...")
        return True

    if subcmd == "spawn":
        if len(parts) < 3:
            err = (
                "\u2717 \u0646\u0627\u0645 "
                "\u0639\u0627\u0645\u0644 \u0644\u0627\u0632\u0645 \u0627\u0633\u062a. "
                "\u0645\u062b\u0627\u0644: /swarm spawn SecurityAgent critic"
            )
            output(cm.red(err))
            return True
        name = parts[2]
        role = parts[3] if len(parts) > 3 else "specialist"
        node = coord.topology.register_node(name=name, role=role)
        succ_spawn = (
            f"\u2713 \u0639\u0627\u0645\u0644 '{node.name}' "
            f"\u0628\u0627 \u0646\u0642\u0634 '{node.role.value}' "
            "\u0627\u0636\u0627\u0641\u0647 "
            "\u0634\u062f."
        )
        output(cm.green(succ_spawn))
        return True

    if subcmd == "reset":
        coord.reset_swarm()
        reset_msg = (
            "\u2713 \u06a9\u0644\u0627\u0633\u062a\u0631 "
            "\u0633\u0648\u0627\u0631\u0645 "
            "\u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a "
            "\u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc "
            "\u0634\u062f."
        )
        output(cm.green(reset_msg))
        return True

    # Help
    help_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /swarm:"
    )
    output(cm.bold(help_title))
    output(
        "  /swarm status                       - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0648\u0636\u0639\u06cc\u062a "
        "\u06a9\u0644\u0627\u0633\u062a\u0631 / Swarm status"
    )
    output(
        "  /swarm run <goal>                   - "
        "\u0627\u062c\u0631\u0627\u06cc \u06af\u0631\u0648\u0647\u06cc "
        "\u062a\u0633\u06a9 / Execute multi-agent plan"
    )
    output(
        "  /swarm vote <proposal>              - "
        "\u0631\u0623\u06cc\u200c\u06af\u06cc\u0631\u06cc "
        "\u0648 \u0627\u062c\u0645\u0627\u0639 / Deliberation & vote"
    )
    output(
        "  /swarm spawn <name> [role]          - "
        "\u0627\u0636\u0627\u0641\u0647 \u06a9\u0631\u062f\u0646 "
        "\u0639\u0627\u0645\u0644 \u062c\u062f\u06cc\u062f / Spawn node"
    )
    output(
        "  /swarm reset                        - "
        "\u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc "
        "\u06a9\u0644\u0627\u0633\u062a\u0631 / Reset cluster"
    )
    return True
