"""Slash command dispatcher for Dream Kernel Lifecycle & Lazy Loading."""

from __future__ import annotations

import shlex

from dream.core.engine import get_dream_kernel


def handle_kernel_command(args_str: str) -> str:
    """Handle /kernel slash commands.

    Usage:
        /kernel status
        /kernel reload
        /kernel subsystems
        /kernel profile
        /kernel reset
    """
    if not args_str.strip():
        return (
            "⚙️ **راهنمای دستورات هسته اجرایی دریم (Dream Kernel Lifecycle):**\n\n"
            "- `/kernel status` : وضعیت سلامت، وضعیت چرخه حیات و زمان راه‌اندازی سرد\n"
            "- `/kernel reload` : بارگذاری مجدد گرم بدون قطعی (Zero-Downtime Hot-Reload)\n"
            "- `/kernel subsystems` : وضعیت بارگذاری تنبل (Lazy-Loading) زیرسیستم‌ها\n"
            "- `/kernel profile` : پروفایل حافظه و بهینه‌سازی مصرف منابع\n"
            "- `/kernel reset` : بازنشانی هسته و پروکسی‌های تنبل"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    kernel = get_dream_kernel()

    if subcmd in ("status", "info"):
        snap = kernel.get_snapshot()
        act = snap.active_subsystems_loaded
        tot = snap.total_subsystems_registered
        lines = [
            f"⚙️ **وضعیت هسته مرکزی دریم (`{snap.kernel_id}`):**",
            f"- وضعیت عملیاتی: `● {snap.state.upper()}` | آپ‌تایم: `{snap.uptime_sec}s`",
            f"- زمان راه‌اندازی اولیه: `{snap.cold_start_time_ms:.2f}ms`",
            f"- ماژول‌های بارگذاری‌شده: `{act}/{tot}`",
            "",
            "**خلاصه مصرف منابع:**",
            f"- نسبت بارگذاری تنبل: `{snap.memory_profile.get('lazy_ratio_pct')}%`",
        ]
        return "\n".join(lines)

    elif subcmd in ("reload", "hotreload"):
        res = kernel.hot_reload()
        return f"🔄 **{res['summary_fa']}** (وضعیت جاری: `{res['state']}`)"

    elif subcmd in ("subsystems", "modules"):
        descriptors = kernel.registry.list_descriptors()
        lines = [f"🧩 **زیرسیستم‌های هسته دریم ({len(descriptors)} مورد):**"]
        for name, d in descriptors.items():
            icon = "🟢" if d.status.value == "active" else "💤"
            lines.append(
                f"- {icon} **{d.display_name_fa}** (`{name}`): `{d.status.value}` "
                f"| فراخوانی‌ها: `{d.total_invocations}`"
            )
        return "\n".join(lines)

    elif subcmd in ("profile", "memory"):
        snap = kernel.get_snapshot()
        mp = snap.memory_profile
        return (
            f"📊 **پروفایل عملکردی و حافظه هسته دریم:**\n"
            f"- شناسه فرآیند (PID): `{mp.get('pid')}`\n"
            f"- زمان بوت سرد: `{mp.get('cold_start_time_ms'):.2f}ms`\n"
            f"- کل زیرسیستم‌ها: `{mp.get('lazy_subsystems_count')}`\n"
            f"- ماژول‌های فعال: `{mp.get('loaded_subsystems_count')}`\n"
            f"- بهینه‌سازی بارگذاری تنبل: `{mp.get('lazy_ratio_pct')}%`"
        )

    elif subcmd == "reset":
        kernel.reset()
        return "🔄 **هسته مرکزی دریم با موفقیت بازنشانی شد.**"

    return f"❌ دستور ناآشنا: `{subcmd}`. برای راهنما `/kernel` را وارد کنید."
