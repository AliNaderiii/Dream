"""Slash command dispatcher for the Duplex Audio Streaming Agent and Realtime Gateway."""

from __future__ import annotations

import shlex

from dream.duplex.engine import get_duplex_engine
from dream.duplex.realtime_gateway import get_realtime_gateway_server
from dream.duplex.types import DuplexConfig
from dream.speech.adapters import get_speech_adapter_registry


async def handle_duplex_command(args_str: str) -> str:
    """Handle /duplex slash commands."""
    if not args_str.strip():
        return (
            "🎙️ **راهنمای دستورات صوتی زنده (Duplex Audio & Realtime Gateway):**\n\n"
            "- `/duplex start [session_id]` : آغاز نشست صوتی بلادرنگ دوطرفه\n"
            "- `/duplex push [session_id] <text>` : ارسال پیام/متن صوتی به نشست\n"
            "- `/duplex interrupt [session_id]` : قطع بلادرنگ صحبت ربات (Barge-In)\n"
            "- `/duplex metrics [session_id]` : مشاهده تاخیر و معیارهای عملکردی\n"
            "- `/duplex transcript [session_id]` : دریافت مشروح گفتگو\n"
            "- `/duplex reset [session_id]` : بازنشانی بافرها و شروع مجدد\n"
            "- `/duplex realtime [start|status|stop]` : مدیریت گیت‌وی Realtime WebSocket\n"
            "- `/duplex adapters [list|benchmark]` : لیست و بنچمارک موتورهای صوتی"
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

    elif subcmd in ("realtime", "gateway"):
        action = parts[1].lower() if len(parts) > 1 else "status"
        server = get_realtime_gateway_server()
        if action == "start":
            res = server.start_server()
            return f"🌐 **سرور Realtime WebSocket فعال شد:** `{res['endpoint_ws']}`"
        elif action == "stop":
            server.stop_server()
            return "🛑 **سرور Realtime WebSocket متوقف شد.**"
        else:
            status = "فعال (Running)" if server.is_running else "غیرفعال (Stopped)"
            return (
                f"🌐 **وضعیت OpenAI Realtime Gateway:**\n"
                f"- وضعیت: `{status}`\n"
                f"- آدرس وب‌سوکت: `ws://{server.host}:{server.port}/v1/realtime`\n"
                f"- نشست‌های فعال: `{len(server.sessions)}`"
            )

    elif subcmd in ("adapters", "engines"):
        action = parts[1].lower() if len(parts) > 1 else "list"
        reg = get_speech_adapter_registry()
        if action in ("benchmark", "bench"):
            results = reg.benchmark_adapters()
            lines = ["⚡ **نتایج بنچمارک موتورهای صوتی:**\n"]
            for r in results:
                name = r["adapter"]
                lat = r["measured_latency_ms"]
                size = r["model_size_mb"]
                lines.append(f"- **{name}**: تاخیر `{lat}ms` (حجم: `{size}MB`)")
            return "\n".join(lines)
        else:
            adapters = reg.list_adapters()
            lines = ["🎙️ **موتورهای صوتی و VAD ثبت‌شده:**\n"]
            for a in adapters:
                role = "TTS" if a["is_tts"] else ("STT" if a["is_stt"] else "VAD")
                lat = a["latency_profile_ms"]
                lines.append(f"- **{a['name']}** `[{role}]` | تاخیر: `{lat}ms`")
            return "\n".join(lines)

    else:
        return f"❌ دستور ناآشنا: `{subcmd}`. برای مشاهده راهنما `/duplex` را وارد کنید."
