"""Slash command dispatcher for the Autonomous Reactive Engine subsystem."""

from __future__ import annotations

import json
import shlex

from dream.reactive.engine import get_reactive_engine


def handle_reactive_command(args_str: str) -> str:
    """Handle /reactive slash commands.

    Usage:
        /reactive rule list
        /reactive rule create <id> <name_fa> <event_type>
        /reactive ingest <event_type> [json_data]
        /reactive history
        /reactive metrics
        /reactive reset
    """
    if not args_str.strip():
        return (
            "⚡ **راهنمای دستورات موتور واکنشی و رویدادمحور (Reactive Engine):**\n\n"
            "- `/reactive rule list` : مشاهده فهرست قوانین فعال واکنشی\n"
            "- `/reactive rule create <id> <name> <event_type>` : ثبت قانون واکنشی جدید\n"
            "- `/reactive ingest <event_type> [json_data]` : ارسال دستی رویداد به باس\n"
            "- `/reactive history` : مشاهده تاریخچه رویدادهای پردازش‌شده\n"
            "- `/reactive metrics` : گزارش کامل آمار و وضعیت مانیتورینگ\n"
            "- `/reactive reset` : بازنشانی باس رویدادها و قوانین"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_reactive_engine()

    if subcmd == "rule":
        if len(parts) < 2:
            return "❌ دستور ناقص است. مثال: `/reactive rule list` یا `/reactive rule create`"
        action = parts[1].lower()
        if action == "list":
            rules = engine.list_rules()
            lines = ["📋 **فهرست قوانین واکنشی فعال:**"]
            for r in rules:
                lines.append(
                    f"- **{r['name_fa']}** (`{r['rule_id']}`) | فراخوانی: `{r['trigger_count']}`"
                )
            return "\n".join(lines)
        elif action == "create":
            if len(parts) < 5:
                return "❌ مشخصات ناقص است: `/reactive rule create <id> <name> <event_type>`"
            rid, name, etype = parts[2], parts[3], parts[4]
            engine.register_rule(rule_id=rid, name_fa=name, event_types=[etype])
            return f"✅ قانون واکنشی **{name}** (`{rid}`) برای رویداد `{etype}` ثبت شد."

    elif subcmd == "ingest":
        if len(parts) < 2:
            return "❌ نوع رویداد را مشخص کنید: `/reactive ingest <event_type> [json_data]`"
        etype = parts[1]
        data = {}
        if len(parts) > 2:
            try:
                data = json.loads(" ".join(parts[2:]))
            except Exception:
                data = {"raw_text": " ".join(parts[2:])}

        ok, payload = engine.ingest_event(source="user:manual", event_type=etype, data=data)
        status_icon = "✅ پردازش شد" if ok else "⚠️ رد شد (تکراری)"
        return f"⚡ **رویداد `{etype}` ثبت شد:** {status_icon}\n- شناسه: `{payload.event_id}`"

    elif subcmd == "history":
        events = engine.bus.get_history(limit=10)
        lines = ["📜 **تاریخچه ۱۰ رویداد اخیر:**"]
        if not events:
            lines.append("_هیچ رویدادی در تاریخچه وجود ندارد._")
        for e in events:
            p_str = e.priority.value.upper()
            lines.append(f"- `[{p_str}]` **{e.event_type}** | وضعیت: `{e.status.value}`")
        return "\n".join(lines)

    elif subcmd == "metrics":
        return engine.export_markdown_report()

    elif subcmd == "reset":
        engine.reset()
        return "🔄 **موتور رویدادمحور و باس رویدادها با موفقیت ریست شدند.**"

    return f"❌ دستور ناآشنا: `{subcmd}`. برای راهنما `/reactive` را بزنید."
