"""CLI and slash command handlers for Interactive Canvas & Visual Artifact Studio."""

from __future__ import annotations

from dream.canvas.tools import (
    canvas_export_bundle,
    canvas_get_artifact,
    canvas_get_status,
    canvas_list_artifacts,
    canvas_reset_session,
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
        return "❌ دستور نامعتبر است."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        # Default help
        return (
            "🎨 دستورات بوم تعاملی (Canvas):\n"
            "  /canvas list                              فهرست آرتیفکت‌ها\n"
            "  /canvas create <type> <title> <code>      ایجاد آرتیفکت جدید\n"
            "  /canvas view <id>                         مشاهده محتوا\n"
            "  /canvas export [markdown|json]            خروجی کل آرتیفکت‌ها\n"
            "  /canvas status                            وضعیت بوم\n"
            "  /canvas reset                             بازنشانی بوم"
        )

    subcmd = parts[1].lower()
    args_str = parts[2] if len(parts) > 2 else ""

    if subcmd == "list":
        res = canvas_list_artifacts()
        artifacts = res.get("artifacts", [])
        if not artifacts:
            return "📜 هیچ آرتیفکتی در بوم فعلی وجود ندارد."
        lines = ["🎨 فهرست آرتیفکت‌های بوم:"]
        for a in artifacts:
            a_id = a["id"]
            a_title = a["title"]
            a_type = a["artifact_type"]
            a_v = a["version"]
            lines.append(f"- `{a_id}`: **{a_title}** ({a_type}, v{a_v})")
        return "\n".join(lines)

    if subcmd == "view":
        art_id = args_str.strip()
        if not art_id:
            return "❌ لطفاً شناسه آرتیفکت را وارد کنید."
        res = canvas_get_artifact(art_id)
        if not res.get("success"):
            return f"❌ {res.get('error')}"
        art = res["artifact"]
        title = art["title"]
        a_id = art["id"]
        v = art["version"]
        lang = art["language"] or art["artifact_type"]
        cnt = art["content"]
        return f"### 📋 {title} (`{a_id}` - v{v})\n```{lang}\n{cnt}\n```"

    if subcmd == "export":
        fmt = args_str.strip() or "markdown"
        res = canvas_export_bundle(format_type=fmt)
        if res.get("success"):
            return res.get("bundle", "")
        return f"❌ {res.get('error')}"

    if subcmd == "status":
        st = canvas_get_status()
        active_id = st.get("active_artifact_id")
        active_str = active_id if active_id else "هیچ"
        return (
            "🗟 وضعیت بوم تعاملی:\n"
            f"- شناسه نشست: {st.get('session_id')}\n"
            f"- تعداد آرتیفکت‌ها: {st.get('total_artifacts')}\n"
            f"- آرتیفکت فعال: {active_str}"
        )

    if subcmd == "reset":
        canvas_reset_session()
        return "✅ بوم تعاملی بازنشانی شد."

    return "❌ زیردستور نامعتبر است. برای راهنما `/canvas` را وارد کنید."
