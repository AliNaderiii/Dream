"""Slash command handlers for Semantic Caching & Token Economics."""

from __future__ import annotations

from dream.cache.tools import (
    cache_clear,
    cache_get_economics,
    cache_lookup_query,
    cache_warmup,
)


def handle_cache_slash_command(command_str: str) -> str:
    """Handle /cache CLI slash commands.

    Usage:
        /cache stats
        /cache clear
        /cache warmup
        /cache lookup <query>
    """
    parts = command_str.strip().split(maxsplit=2)
    if len(parts) < 2:
        return (
            "💾 دستورات کش معنایی و مدیریت توکن (Cache & Token Economics):\n"
            "  /cache stats                      گزارش آمار صرفه‌جویی توکن و هزینه\n"
            "  /cache clear                      پاکسازی حافظه کش\n"
            "  /cache warmup                     آماده‌سازی پاسخ‌های پیش‌فرض\n"
            "  /cache lookup <query>             جستجوی معنایی در کش"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "stats":
        econ = cache_get_economics()
        hits = econ.get("total_hits", 0)
        reqs = econ.get("total_requests", 0)
        ratio = econ.get("hit_ratio", 0.0) * 100
        tokens = econ.get("total_tokens_saved", 0)
        cost = econ.get("estimated_cost_saved_usd", 0.0)
        latency = econ.get("total_latency_saved_ms", 0.0) / 1000.0

        return (
            "📊 گزارش اقتصاد توکن و کش معنایی:\n"
            f"- تعداد درخواست‌ها: {reqs} (اصابت‌ها: {hits} | نرخ اصابت: {ratio:.1f}%)\n"
            f"- توکن‌های صرفه‌جویی‌شده: {tokens:,} توکن\n"
            f"- کاهش تاخیر (Latency Saved): {latency:.2f} ثانیه\n"
            f"- صرفه‌جویی مالی تخمینی: ${cost:.4f} USD\n"
            f"- تعداد پاسخ‌های فعال در کش: {econ.get('active_entries_count', 0)}"
        )

    if subcommand == "clear":
        res = cache_clear()
        cnt = res.get("cleared_entries_count", 0)
        return f"✅ حافظه کش پاکسازی شد. ({cnt} مورد حذف گردید)"

    if subcommand == "warmup":
        res = cache_warmup()
        cnt = res.get("warmed_up_count", 0)
        return f"✅ تعداد {cnt} پاسخ پیش‌فرض در کش بارگذاری شد."

    if subcommand == "lookup":
        if not arg:
            return "❌ لطفاً عبارت جستجو را وارد کنید."
        res = cache_lookup_query(arg)
        if res.get("hit"):
            tier = res.get("tier")
            sim = res.get("similarity_score", 0)
            return (
                f"🎯 اصابت به کش ({tier} - شباهت: {sim:.2f}):\n"
                f"{res.get('response')}"
            )
        return "❌ موردی در کش یافت نشد (Cache Miss)."

    return f"❌ زیردستور ناشناخته '{subcommand}'. برای راهنما '/cache' را بزنید."
