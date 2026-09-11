"""CLI and slash command handlers for Interactive Canvas & Visual Artifact Studio."""

from __future__ import annotations

from typing import Any

from dream.canvas.tools import (
    canvas_create_artifact,
    canvas_diff_versions,
    canvas_export_bundle,
    canvas_get_artifact,
    canvas_get_status,
    canvas_list_artifacts,
    canvas_reset_session,
    canvas_update_artifact,
)


def handle_canvas_slash_command(command_str: str) -> str:
    """Handle /canvas slash commands for REPL and CLI interface.

    Usage:
        /canvas list
        /canvas create <type> <title> <code>
        /canvas update <artifact_id> <code>
        /canvas view <artifact_id>
        /canvas diff <artifact_id> <v1> <v2>
        /canvas export [markdown|json]
        /canvas reset
        /canvas status
    """
    cmd = command_str.strip()
    if not cmd.startswith("/canvas"):
        return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        # Default help
        return (
            "\U0001f3a8 \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc (Canvas):\n"
            "  /canvas list                              \u0641\u0647\u0631\u0633\u062a \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627\n"
            "  /canvas create <type> <title> <code>      \u0627\u06cc\u062c\u0627\u062f \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a \u062c\u062f\u06cc\u062f\n"
            "  /canvas view <id>                         \u0645\u0634\u0627\u0647\u062f\u0647 \u0645\u062d\u062a\u0648\u0627\n"
            "  /canvas export [markdown|json]            \u062e\u0631\u0648\u062c\u06cc \u06a9\u0644 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627\n"
            "  /canvas status                            \u0648\u0636\u0639\u06cc\u062a \u0628\u0648\u0645\n"
            "  /canvas reset                             \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0628\u0648\u0645"
        )

    subcmd = parts[1].lower()
    args_str = parts[2] if len(parts) > 2 else ""

    if subcmd == "list":
        res = canvas_list_artifacts()
        artifacts = res.get("artifacts", [])
        if not artifacts:
            return "\U0001f4dc \u0647\u06cc\u0686 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u06cc \u062f\u0631 \u0628\u0648\u0645 \u0641\u0639\u0644\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f."
        lines = ["\U0001f3a8 \u0641\u0647\u0631\u0633\u062a \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627\u06cc \u0628\u0648\u0645:"]
        for a in artifacts:
            lines.append(f"- `{a['id']}`: **{a['title']}** ({a['artifact_type']}, v{a['version']})")
        return "\n".join(lines)

    if subcmd == "view":
        art_id = args_str.strip()
        if not art_id:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0634\u0646\u0627\u0633\u0647 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = canvas_get_artifact(art_id)
        if not res.get("success"):
            return f"\u274c {res.get('error')}"
        art = res["artifact"]
        return f"### \U0001f4cb {art['title']} (`{art['id']}` - v{art['version']})\n```{art['language'] or art['artifact_type']}\n{art['content']}\n```"

    if subcmd == "export":
        fmt = args_str.strip() or "markdown"
        res = canvas_export_bundle(format_type=fmt)
        if res.get("success"):
            return res.get("bundle", "")
        return f"\u274c {res.get('error')}"

    if subcmd == "status":
        st = canvas_get_status()
        return (
            f"\U0001f4df \u0648\u0636\u0639\u06cc\u062a \u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc:\n"
            f"- \u0634\u0646\u0627\u0633\u0647 \u0646\u0634\u0633\u062a: {st.get('session_id')}\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627: {st.get('total_artifacts')}\n"
            f"- \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a \u0641\u0639\u0627\u0644: {st.get('active_artifact_id') or '\u0647\u06cc\u0686'}"
        )

    if subcmd == "reset":
        canvas_reset_session()
        return "\u2705 \u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

    return "\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a. \u0628\u0631\u0627\u06cc \u0631\u0627\u0647\u0646\u0645\u0627 `/canvas` \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
