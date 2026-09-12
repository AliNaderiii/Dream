"""Slash command dispatcher for Telephony and VoIP calls."""

from __future__ import annotations

import shlex

from dream.telephony.engine import get_telephony_engine


async def handle_telephony_command(args_str: str) -> str:
    """Handle /call slash commands."""
    if not args_str.strip():
        return (
            "📞 **راهنمای دستورات تلفن و تماس هوشمند (Telephony Gateway):**\n\n"
            "- `/call dial <number>` : برقراری تماس صوتی خروجی با شماره مقصد\n"
            "- `/call status <call_id>` : بررسی وضعیت زنده تماس\n"
            "- `/call hangup <call_id>` : قطع تماس فعال\n"
            "- `/call list` : مشاهده لیست تماس‌های اخیر\n"
            "- `/call record <call_id>` : دریافت گزارش مشروح و هزینه تماس"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_telephony_engine()

    if subcmd in ("dial", "call", "outbound"):
        if len(parts) < 2:
            return "❌ لطفاً شماره مقصد را مشخص کنید: `/call dial <شماره>`"
        to_number = parts[1]
        record = engine.initiate_outbound_call(to_number=to_number)
        return (
            f"📞 **تماس برقرار شد:**\n"
            f"- شناسه: `{record.call_id}`\n"
            f"- مقصد: `{record.to_number}`\n"
            f"- وضعیت: `{record.status.value}`"
        )

    elif subcmd == "status":
        if len(parts) < 2:
            return "❌ لطفاً شناسه تماس را وارد کنید: `/call status <call_id>`"
        call_id = parts[1]
        record = engine.get_call(call_id)
        if not record:
            return f"❌ تماس `{call_id}` یافت نشد."
        return (
            f"📊 **وضعیت تماس `{call_id}`:**\n"
            f"- وضعیت: `{record.status.value}`\n"
            f"- مدت: `{record.duration_sec:.1f}s`\n"
            f"- هزینه: `${record.cost_estimated_usd:.4f}`"
        )

    elif subcmd in ("hangup", "end", "stop"):
        if len(parts) < 2:
            return "❌ لطفاً شناسه تماس را وارد کنید: `/call hangup <call_id>`"
        call_id = parts[1]
        success = engine.hangup_call(call_id)
        if not success:
            return f"❌ تماس `{call_id}` یافت نشد."
        return f"🛑 **تماس `{call_id}` با موفقیت قطع شد.**"

    elif subcmd in ("list", "history"):
        calls = engine.list_calls()
        if not calls:
            return "ℹ️ هیچ تماسی در سابقه ثبت نشده است."
        lines = ["📞 **لیست تماس‌های اخیر:**\n"]
        for c in calls[:10]:
            cid = c["call_id"]
            to_n = c["to_number"]
            st = c["status"]
            lines.append(f"- `{cid}`: {c['direction']} به {to_n} ({st})")
        return "\n".join(lines)

    elif subcmd in ("record", "report", "transcript"):
        if len(parts) < 2:
            return "❌ لطفاً شناسه تماس را وارد کنید: `/call record <call_id>`"
        call_id = parts[1]
        return engine.export_call_record(call_id)

    else:
        return f"❌ دستور ناآشنا: `{subcmd}`. برای مشاهده راهنما `/call` را وارد کنید."
