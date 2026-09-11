"""Slash command handlers for `/compress` and `/fast` modes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.compression.fast_mode import get_fast_mode_controller
from dream.compression.strategies import compress_messages


def handle_compress_command(
    args: str,
    messages: list[dict[str, Any]] | None = None,
    output: Callable[[str], None] = print,
) -> tuple[list[dict[str, Any]], bool]:
    """Process `/compress` command to manually optimize and compact conversation history.

    Usage:
        /compress
        /compress lossy
        /compress code
        /compress hybrid
        /compress hybrid 2
    """
    history = messages or []
    if not history:
        output("ℹ️ تاریخچه گفتگویی برای فشرده‌سازی وجود ندارد.")
        return [], True

    parts = args.strip().split()
    strat = "hybrid"
    keep_recent = 4

    if parts:
        first = parts[0].lower()
        if first in ("lossy", "code", "hybrid"):
            strat = first
            if len(parts) > 1 and parts[1].isdigit():
                keep_recent = int(parts[1])
        elif first.isdigit():
            keep_recent = int(first)

    new_messages, res = compress_messages(
        history,
        strategy=strat,
        keep_recent=keep_recent,
        reason=f"slash_compress_{strat}",
    )

    if res.compacted:
        output(
            f"🗜️ **فشرده‌سازی کانتکست با استراتژی `{strat}` انجام شد:**\n"
            f"  • تعداد پیام‌های آرشیو شده: {res.dropped_messages_count}\n"
            f"  • توکن‌های صرفه‌جویی‌شده: ~{res.tokens_saved} توکن\n"
            f"  • توکن‌های کانتکست: {res.tokens_before} ➔ {res.tokens_after}"
        )
    else:
        output(f"ℹ️ نیازی به فشرده‌سازی نبود ({res.reason}).")

    return new_messages, True


def handle_fast_command(
    args: str,
    output: Callable[[str], None] = print,
) -> bool:
    """Process `/fast` command to control execution latency profiles.

    Usage:
        /fast
        /fast auto
        /fast cold
        /fast turbo
        /fast status
    """
    controller = get_fast_mode_controller()
    parts = args.strip().split()

    if not parts or parts[0].lower() in ("status", "info"):
        current = controller.mode
        output(
            f"⚡ **وضعیت حالت سریع (Fast Mode): `{current.value.upper()}`**\n"
            f"  • `auto`: انتخاب خودکار و تطبیقی مدل و عمق استنتاج\n"
            f"  • `cold`: حداکثر عمق استدلال و کانتکست کامل (استاندارد)\n"
            f"  • `turbo`: کمترین زمان پاسخ (Ultra Low Latency) با خروجی خلاصه"
        )
        return True

    target = parts[0].lower()
    if target in ("auto", "cold", "turbo"):
        new_mode = controller.set_mode(target)
        output(f"⚡ حالت اجرای ایجنت به **{new_mode.value.upper()}** تغییر یافت.")
        return True

    output("❌ مقدار نامعتبر برای `/fast`. مقادیر مجاز: `auto`، `cold`، `turbo`")
    return True
