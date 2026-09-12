"""Slash command dispatcher for the Unified Web Dashboard & Control Tower."""

from __future__ import annotations

import shlex

from dream.dashboard.engine import get_dashboard_engine


def handle_dashboard_command(args_str: str) -> str:
    """Handle /dashboard slash commands.

    Usage:
        /dashboard overview
        /dashboard subsystem <name>
        /dashboard html [theme] [locale]
        /dashboard report
        /dashboard alerts
        /dashboard reset
    """
    if not args_str.strip():
        return (
            "🎛️ **راهنمای دستورات برج مراقبت و داشبورد مدیریتی (Control Tower):**\n\n"
            "- `/dashboard overview` : خلاصه وضعیت اجرایی تمامی زیرسیستم‌ها\n"
            "- `/dashboard subsystem <name>` : متریک‌های تفصیلی یک زیرسیستم\n"
            "- `/dashboard html [theme] [locale]` : تولید پیش‌نمایش بصری HTML/SVG\n"
            "- `/dashboard report` : جدول متنی جامع سلامت و متریک‌های سیستم\n"
            "- `/dashboard alerts` : مشاهده هشدارهای فعال سیستم\n"
            "- `/dashboard reset` : بازنشانی مانیتورینگ برج مراقبت"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_dashboard_engine()

    if subcmd == "overview":
        ov = engine.get_overview()
        lines = [
            "🎛️ **خلاصه وضعیت برج مراقبت (Control Tower):**",
            f"- وضعیت کلی سلامت: `● {ov['overall_health'].upper()}`",
            f"- تعداد زیرسیستم‌ها: `{ov['healthy_subsystems']}/{ov['total_subsystems']}` سالم",
            f"- هشدارهای فعال: `{ov['active_alerts_count']}`",
            "",
            "**وضعیت زیرسیستم‌ها:**",
        ]
        for name, info in ov["subsystems_overview"].items():
            icon = "🟢" if info["status"] == "healthy" else "🟡"
            lines.append(f"- {icon} **{name}**: `{info['status']}` (تعداد: {info['active_count']})")
        return "\n".join(lines)

    elif subcmd == "subsystem":
        if len(parts) < 2:
            return "❌ نام زیرسیستم را مشخص کنید: `/dashboard subsystem <name>`"
        name = parts[1]
        res = engine.get_subsystem_telemetry(name)
        if not res["success"]:
            return f"❌ {res['error']}"
        s = res["subsystem"]
        lines = [
            f"📊 **متریک‌های زیرسیستم {s['display_name_fa']} (`{s['name']}`):**",
            f"- وضعیت: `{s['status']}` | آپ‌تایم: `{s['uptime_sec']}s`",
            f"- آیتم‌های فعال: `{s['active_items_count']}`",
            "",
            "**شاخص‌ها:**",
        ]
        for k, v in s["metrics"].items():
            lines.append(f"- `{k}`: `{v}`")
        return "\n".join(lines)

    elif subcmd == "html":
        theme = parts[1] if len(parts) > 1 else "dark"
        locale = parts[2] if len(parts) > 2 else "fa"
        html = engine.render_html(theme=theme, locale=locale)
        return (
            f"🖥️ **داشبورد بصری HTML/SVG با تم `{theme}` ایجاد شد** ({len(html):,} کاراکتر).\n"
            f"جهت ذخیره و مشاهده می‌توانید از ابزار `canvas` یا پیش‌نمایش استفاده فرمایید."
        )

    elif subcmd in ("report", "metrics"):
        return engine.export_metrics_markdown()

    elif subcmd == "alerts":
        snap = engine.get_snapshot()
        if not snap.active_alerts:
            return "✅ **هیچ هشدار فعالی در سیستم وجود ندارد.**"
        lines = ["⚠️ **هشدارهای فعال در سامانه:**"]
        for a in snap.active_alerts:
            lines.append(f"- `[{a.severity.upper()}]` **{a.subsystem}**: {a.message_fa}")
        return "\n".join(lines)

    elif subcmd == "reset":
        engine.reset()
        return "🔄 **برج مراقبت داشبورد با موفقیت بازنشانی شد.**"

    return f"❌ دستور ناآشنا: `{subcmd}`. برای راهنما `/dashboard` را وارد کنید."
