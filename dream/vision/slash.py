"""Slash command dispatcher for Multi-Modal Vision & Video Stream Reasoning."""

from __future__ import annotations

import shlex

from dream.vision.engine import get_vision_engine


def handle_vision_command(args_str: str) -> str:
    """Handle /vision slash commands.

    Usage:
        /vision analyze <descriptor>
        /vision video <video_id> [duration_sec]
        /vision diagram <mermaid_code>
        /vision memory
        /vision metrics
        /vision reset
    """
    if not args_str.strip():
        return (
            "👁️ **راهنمای دستورات بینایی چندوجهی و ویدیو (Multi-Modal Vision):**\n\n"
            "- `/vision analyze <desc>` : تحلیل تصویر و ثبت در حافظه مکانی\n"
            "- `/vision video <video_id> [sec]` : تفکیک فریم‌های کلیدی و صحنه‌های ویدیو\n"
            "- `/vision diagram <code/svg>` : اعتبارسنجی ساختاری فلوچارت یا نمودار\n"
            "- `/vision memory` : نمایش موجودیت‌های بصری در حافظه مکانی\n"
            "- `/vision metrics` : تله‌متری و وضعیت سامانه بینایی\n"
            "- `/vision reset` : بازنشانی حافظه مکانی بینایی"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_vision_engine()

    if subcmd == "analyze":
        desc = " ".join(parts[1:]) if len(parts) > 1 else "تصویر ورودی بدون شرح"
        res = engine.analyze_image(
            image_descriptor=desc,
            detected_objects=[
                {
                    "label_fa": "عنصر اصلی",
                    "category": "object",
                    "box": {"ymin": 0.2, "xmin": 0.3, "ymax": 0.8, "xmax": 0.7},
                },
            ],
        )
        return f"👁️ **تحلیل تصویر انجام شد:** {res['summary_fa']}"

    elif subcmd == "video":
        if len(parts) < 2:
            return "❌ شناسه ویدیو را مشخص کنید: `/vision video <video_id> [sec]`"
        vid = parts[1]
        dur = float(parts[2]) if len(parts) > 2 else 10.0
        tl = engine.decompose_video(video_id=vid, duration_sec=dur)
        lines = [
            f"🎬 **تجزیه جریان ویدیویی (`{vid}`):**",
            f"- مدت: `{tl.duration_sec}s` | فریم‌ها: `{len(tl.keyframes)}` | صحنه: {tl.scene_count}",
        ]
        lines.extend([
            "",
            "**فریم‌های کلیدی شناسایی‌شده:**",
        ])
        for kf in tl.keyframes[:5]:
            lines.append(f"- ⏱️ `{kf.timestamp_sec}s` (صحنه {kf.scene_id}): {kf.caption_fa}")
        return "\n".join(lines)

    elif subcmd == "diagram":
        code = " ".join(parts[1:]) if len(parts) > 1 else "graph TD\nA-->B"
        diag = engine.inspect_diagram(code, diagram_format="mermaid")
        if not diag.get("valid"):
            return f"❌ خطای دیاگرام: {diag.get('error')}"
        has_fa = "بله" if diag["has_persian_text"] else "خیر"
        t_type = diag["diagram_type"]
        n_cnt = diag["total_nodes"]
        e_cnt = diag["total_edges"]
        return (
            f"📊 **تحلیل ساختاری دیاگرام:**\n"
            f"- نوع: `{t_type}` | گره: `{n_cnt}` | یال: `{e_cnt}`\n"
            f"- پشتیبانی از متن فارسی: `{has_fa}`"
        )

    elif subcmd in ("memory", "spatial"):
        ents = engine.spatial_memory.list_entities()
        if not ents:
            return "ℹ️ **حافظه مکانی-بصری خالی است.**"
        lines = [f"🧠 **موجودیت‌های فعال در حافظه مکانی ({len(ents)} مورد):**"]
        for e in ents:
            c_str = f"({e.box.center_x}, {e.box.center_y})"
            lines.append(f"- `{e.entity_id}` | **{e.label_fa}** ({e.category}) در مرکز: `{c_str}`")
        return "\n".join(lines)

    elif subcmd == "metrics":
        m = engine.get_metrics()
        return (
            f"📊 **تله‌متری سامانه بینایی:**\n"
            f"- وضعیت: `🟢 {m['status'].upper()}`\n"
            f"- مجموع تحلیل‌ها: `{m['total_analyses_count']}`\n"
            f"- اشیاء در حافظه مکانی: `{m['spatial_entities_in_memory']}`\n"
            f"- آپ‌تایم: `{m['uptime_sec']}s`"
        )

    elif subcmd == "reset":
        engine.reset()
        return "🔄 **حافظه مکانی و موتور بینایی با موفقیت بازنشانی شد.**"

    return f"❌ دستور ناآشنا: `{subcmd}`. برای راهنما `/vision` را وارد کنید."
