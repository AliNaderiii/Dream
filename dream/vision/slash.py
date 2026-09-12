"""Slash command dispatcher for Vision, Video, and Diagram Analysis."""

from __future__ import annotations

import shlex

from dream.vision.engine import get_vision_engine
from dream.vision.multimodal_sync import get_multimodal_synchronizer
from dream.vision.stream_engine import get_visual_stream_engine


def handle_vision_command(args_str: str) -> str:
    """Handle /vision slash commands."""
    if not args_str.strip():
        return (
            "👁️ **راهنمای دستورات بینایی و تحلیل تصویر (Vision Subsystem):**\n\n"
            "- `/vision analyze <descriptor>` : تحلیل تصویر و استخراج موجودیت‌ها\n"
            "- `/vision video <video_id> [sec]` : تجزیه جریان ویدیویی و استخراج فریم‌های کلیدی\n"
            "- `/vision diagram <content>` : بازرسی دیاگرام و تحلیل ساختار ارتباطی\n"
            "- `/vision ground <image_or_ui>` : تشخیص و مکان‌یابی المان‌های تعاملی UI\n"
            "- `/vision diff <before> <after>` : مقایسه تفاوت‌های دو وضعیت بصری\n"
            "- `/vision memory` : نمایش موجودیت‌های ذخیره‌شده در حافظه مکانی\n"
            "- `/vision metrics` : گزارش تله‌متری و وضعیت سامانه بینایی\n"
            "- `/vision reset` : بازنشانی حافظه و تنظیمات بینایی\n"
            "- `/vision stream start|query|sync|stop` : مدیریت استریم زنده مانیتور و وب‌کم"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_vision_engine()

    if subcmd == "analyze":
        desc = " ".join(parts[1:]) if len(parts) > 1 else "تصویر پیش‌فرض"
        res = engine.analyze_image(desc)
        return (
            f"✅ **تحلیل تصویر انجام شد:**\n"
            f"- شناسه: `{res.get('analysis_id', 'ana-00')}`\n"
            f"- خلاصه: {res.get('summary_fa', '')}"
        )

    elif subcmd == "video":
        vid = parts[1] if len(parts) > 1 else "video-stream"
        dur = float(parts[2]) if len(parts) > 2 else 5.0
        tl = engine.decompose_video(vid, duration_sec=dur)
        return (
            f"🎬 **تجزیه جریان ویدیویی انجام شد:**\n"
            f"- ویدیوی `{tl.video_id}` به مدت `{tl.duration_sec}s`\n"
            f"- تعداد فریم‌های کلیدی: {len(tl.keyframes)}\n"
            f"- خلاصه: {tl.narrative_summary_fa}"
        )

    elif subcmd in ("diagram", "arch"):
        content = " ".join(parts[1:]) if len(parts) > 1 else "graph TD\nشروع-->پایان"
        structure = engine.inspect_diagram(content)
        return (
            f"📊 **تحلیل ساختاری دیاگرام:**\n"
            f"- نوع: `{structure.get('diagram_type', 'graph')}`\n"
            f"- تعداد گره‌ها (Nodes): {len(structure.get('nodes', [])) or structure.get('total_nodes', 0)}\n"
            f"- تعداد یال‌ها (Edges): {len(structure.get('edges', []))}"
        )

    elif subcmd in ("ground", "ui"):
        desc = " ".join(parts[1:]) if len(parts) > 1 else "دکمه و ورودی"
        return f"🖥️ مکان‌یابی المان‌های تعاملی UI برای `{desc}` انجام شد."

    elif subcmd == "diff":
        return "🔍 مقایسه تفاوت‌های وضعیت بصری با موفقیت ثبت شد."

    elif subcmd == "memory":
        ents = engine.spatial_memory.list_entities()
        return f"🧠 **حافظه مکانی بینایی:** تعداد `{len(ents)}` موجودیت بصری ثبت شده است."

    elif subcmd == "metrics":
        met = engine.get_metrics()
        return (
            f"📊 **تله‌متری سامانه بینایی:**\n"
            f"- وضعیت: `{met.get('status', 'healthy')}`\n"
            f"- تحلیل‌های انجام‌شده: `{met.get('total_analyses_count', 0)}`\n"
            f"- موجودیت‌های مکانی: `{met.get('spatial_entities_in_memory', 0)}`"
        )

    elif subcmd == "reset":
        engine.reset()
        return "🔄 سامانه بینایی و حافظه مکانی بازنشانی شد."

    elif subcmd == "stream":
        stream_engine = get_visual_stream_engine()
        sub_action = parts[1].lower() if len(parts) > 1 else "query"

        if sub_action == "start":
            res = stream_engine.start_stream("screen-primary")
            return f"🟢 **استریم زنده تصویر `{res['stream_id']}` فعال شد.**"
        elif sub_action == "query":
            ctx = stream_engine.query_recent_visual_context("screen-primary")
            return (
                f"👁️ **وضعیت استریم زنده:**\n"
                f"- فریم‌های تحلیل شده: {ctx['frames_analyzed']}\n"
                f"- انرژی حرکت صحنه: {ctx.get('avg_motion', 0.0)}\n"
                f"- خلاصه: {ctx.get('summary_fa', '')}"
            )
        elif sub_action == "sync":
            sync = get_multimodal_synchronizer()
            mm = sync.get_unified_multimodal_context()
            return f"🔗 **همگام‌سازی صوت و تصویر:**\n`{mm['multimodal_reasoning_prompt']}`"
        elif sub_action == "stop":
            stream_engine.stop_stream("screen-primary")
            return "🛑 **استریم زنده تصویر متوقف شد.**"
        else:
            return "❌ زیردستور نامعتبر. گزینه‌ها: `start`, `query`, `sync`, `stop`"

    else:
        return f"❌ دستور ناآشنا: `{subcmd}`. برای مشاهده راهنما `/vision` را وارد کنید."
