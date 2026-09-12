"""Slash command dispatcher for the Duplex Audio Streaming Agent."""

from __future__ import annotations

import shlex

from dream.duplex.engine import get_duplex_engine
from dream.duplex.types import DuplexConfig


async def handle_duplex_command(args_str: str) -> str:
    """Handle /duplex slash commands.

    Usage:
        /duplex start [session_id]
        /duplex push [session_id] <user_text>
        /duplex interrupt [session_id]
        /duplex metrics [session_id]
        /duplex transcript [session_id]
        /duplex reset [session_id]
    """
    if not args_str.strip():
        return (
            "🎙️ **راهنمای دستورات صوتی زنده (Duplex Audio):**\n\n"
            "- `/duplex start [session_id]` : آغاز نشست صوتی بلادرنگ دوطرفه\n"
            "- `/duplex push [session_id] <text>` : ارسال پیام/متن صوتی به نشست\n"
            "- `/duplex interrupt [session_id]` : قطع بلادرنگ صحبت ربات (Barge-In)\n"
            "- `/duplex metrics [session_id]` : مشاهده تاخیر و معیارهای عملکردی\n"
            "- `/duplex transcript [session_id]` : دریافت مشروح گفتگو به همراه وضعیت قطع‌شدگی\n"
            "- `/duplex reset [session_id]` : بازنشانی بافرها و شروع مجدد"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_duplex_engine()

    if subcmd == "start":
        session_id = parts[1] if len(parts) > 1 else "default-duplex"
        cfg = DuplexConfig(session_id=session_id)
        session = engine.get_or_create_session(session_id=session_id, config=cfg)
        await session.start()
        return f"✅ **نشست صوتی دوطرفه `{session_id}` با موفقیت فعال شد.** (آماده دریافت استریم)"

    elif subcmd == "push":
        if len(parts) < 2:
            return "❌ لطفاً متن یا ورودی صوتی را مشخص کنید: `/duplex push [session_id] <متن>`"
        if len(parts) >= 3:
            session_id = parts[1]
            text = " ".join(parts[2:])
        else:
            session_id = "default-duplex"
            text = parts[1]

        session = engine.get_or_create_session(session_id=session_id)
        session.set_user_text(text)
        # Simulate active speech frame
        raw_bytes = b"\x20\x30" * 320
        state, interrupted = await session.push_user_audio(raw_bytes)
        return (
            f"📥 **پیام صوتی دریافت شد** در نشست `{session_id}`:\n"
            f"> *{text}*\n"
            f"- وضعیت کنونی: `{state.value}` | قطع‌شدگی (Barge-in): `{interrupted}`"
        )

    elif subcmd in ("interrupt", "stop"):
        session_id = parts[1] if len(parts) > 1 else "default-duplex"
        session = engine.get_or_create_session(session_id=session_id)
        await session.interrupt_manually()
        return f"⚠️ **صحبت دستیار در نشست `{session_id}` بلافاصله قطع شد (Barge-in).**"

    elif subcmd == "metrics":
        session_id = parts[1] if len(parts) > 1 else "default-duplex"
        session = engine.get_or_create_session(session_id=session_id)
        m = session.metrics
        t_user = m.total_user_audio_sec
        t_bot = m.total_assistant_audio_sec
        return (
            f"📊 **معیارهای تاخیر نشست `{session_id}`:**\n"
            f"- نوبت‌ها: `{m.total_turns}` (کاربر: `{m.user_turns}` | مدل: `{m.assistant_turns}`)\n"
            f"- قطع‌شدن‌ها (Barge-in): `{m.total_interruptions}`\n"
            f"- میانگین TTFT: `{m.avg_ttft_ms:.1f}ms`\n"
            f"- مدت صوت: کاربر `{t_user:.1f}s` | مدل `{t_bot:.1f}s`"
        )

    elif subcmd in ("transcript", "report"):
        session_id = parts[1] if len(parts) > 1 else "default-duplex"
        return engine.export_transcript_markdown(session_id)

    elif subcmd == "reset":
        session_id = parts[1] if len(parts) > 1 else "default-duplex"
        await engine.close_session(session_id)
        return f"🔄 **نشست `{session_id}` به طور کامل ریست شد.**"

    else:
        return f"❌ دستور ناآشنا: `{subcmd}`. برای مشاهده راهنما `/duplex` را وارد کنید."
