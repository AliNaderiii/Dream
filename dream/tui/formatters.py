"""Rich text and visual formatters for tools, memory, subagents, and context files."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from dream.tui.colors import ColorManager


def truncate_text(text: str, limit: int = 120) -> str:
    """Truncate text safely with ellipsis."""
    text_clean = text.replace("\n", " ").strip()
    if len(text_clean) <= limit:
        return text_clean
    return text_clean[: limit - 3] + "..."


def format_tool_line(
    name: str,
    arguments: dict[str, Any],
    result: str,
    colors: ColorManager | None = None,
) -> str:
    """Format a tool invocation and outcome line."""
    cm = colors or ColorManager()
    status_icon, status_label = _call_status(result)

    args_rendered = ", ".join(
        f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in arguments.items()
    )
    truncated_args = truncate_text(args_rendered, 60)
    truncated_result = truncate_text(result, 80)

    if status_icon == "✓":
        tag = cm.green(f"[{status_label}]")
    elif status_icon == "✗":
        tag = cm.red(f"[{status_label}]")
    else:
        tag = cm.yellow(f"[{status_label}]")

    return f"{tag} {cm.bold(name)}({truncated_args}) → {truncated_result}"


def _call_status(result: str) -> tuple[str, str]:
    """Classify tool result into icon and label."""
    try:
        parsed = json.loads(result)
        if isinstance(parsed, dict) and parsed.get("status") == "error":
            return "✗", "tool:error"
    except Exception:
        pass
    if "refused" in result.lower() or "denied" in result.lower():
        return "!", "tool:refused"
    return "✓", "tool:ok"


def format_extraction_line(result: Any, colors: ColorManager | None = None) -> str:
    """Format memory extraction outcome."""
    cm = colors or ColorManager()
    if not result:
        return cm.dim("[memory] no facts extracted")
    if isinstance(result, list):
        items = [truncate_text(str(r), 50) for r in result]
        return cm.cyan(f"[memory:learned] {len(result)} facts: {', '.join(items)}")
    return cm.cyan(f"[memory:learned] {truncate_text(str(result), 80)}")


def format_context_files_table(
    files_usage: dict[str, dict[str, Any]],
    colors: ColorManager | None = None,
) -> str:
    """Render a visual table with usage meters for Tier-4 context files."""
    cm = colors or ColorManager()
    lines = [
        cm.bold("📁 Tier-4 Persistent Context Files"),
        cm.dim("─" * 65),
    ]
    for filename, stats in files_usage.items():
        chars = stats.get("chars", 0)
        max_chars = stats.get("max_chars", 2000)
        description = stats.get("description", "")
        meter = cm.render_meter(chars, max_chars, width=15)
        lines.append(f"  {cm.bold(filename):<12} {meter:<30} {cm.dim(description)}")
    lines.append(cm.dim("─" * 65))
    return "\n".join(lines)


def format_subagents_table(
    subagents_list: list[dict[str, Any]],
    colors: ColorManager | None = None,
) -> str:
    """Render subagents status table."""
    cm = colors or ColorManager()
    if not subagents_list:
        return cm.dim("No active subagent workflows currently running.")

    lines = [
        cm.bold("🤖 Subagents & Multi-Agent Swarm Status"),
        cm.dim("─" * 70),
        f"  {'ID':<10} {'Role':<15} {'Status':<12} {'Description':<30}",
        cm.dim("─" * 70),
    ]
    for sub in subagents_list:
        sub_id = sub.get("id", "sub-0")
        role = sub.get("role", "worker")
        status = sub.get("status", "idle")
        desc = truncate_text(sub.get("description", ""), 30)

        is_active = status in ("completed", "running")
        status_colored = cm.green(status) if is_active else cm.yellow(status)
        lines.append(f"  {sub_id:<10} {cm.bold(role):<15} {status_colored:<21} {desc:<30}")
    lines.append(cm.dim("─" * 70))
    return "\n".join(lines)


def report_turn_activity(
    turn: Any,
    output: Callable[[str], None] | None = None,
    colors: ColorManager | None = None,
) -> None:
    """Report tool execution and extraction activity from a Turn to output."""
    out = output or print
    cm = colors or ColorManager()

    # Tool calls
    if hasattr(turn, "tool_calls") and turn.tool_calls:
        for call in turn.tool_calls:
            name = call.get("name", "unknown")
            args = call.get("arguments", {})
            result = str(call.get("result", ""))
            out(format_tool_line(name, args, result, cm))

    # Extraction
    if hasattr(turn, "extraction") and turn.extraction:
        out(format_extraction_line(turn.extraction, cm))
