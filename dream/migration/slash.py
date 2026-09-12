"""CLI and slash command handlers for the Universal Migration Subsystem."""

from __future__ import annotations

from dream.migration.tools import (
    migration_analyze_source,
    migration_execute,
    migration_export_report,
    migration_get_status,
    migration_reset,
)


def handle_migration_slash_command(command_str: str) -> str:
    """Handle /migrate CLI slash commands for agent workspace transition.

    Usage:
        /migrate analyze <path>
        /migrate hermes <path> [--dry]
        /migrate openclaw <path> [--dry]
        /migrate report
        /migrate status
        /migrate reset
    """
    cmd = command_str.strip()
    if not cmd.startswith("/migrate"):
        return "❌ دستور نامعتبر است."

    parts = cmd[len("/migrate") :].strip().split()
    if not parts:
        return (
            "🛠️ **راهنمای دستورات مهاجرت به Dream (/migrate):**\n"
            "- `/migrate analyze <path>`: تحلیل و پیش‌نمایش فایل‌های قابل انتقال\n"
            "- `/migrate hermes <path>`: انتقال کامل حافظه و مهارت‌ها از Hermes Agent\n"
            "- `/migrate openclaw <path>`: انتقال اطلاعات از چارچوب OpenClaw\n"
            "- `/migrate report`: مشاهده گزارش آخرین عملیات مهاجرت\n"
            "- `/migrate status`: نمایش وضعیت و آمار کلی مهاجرت‌ها\n"
            "- `/migrate reset`: بازنشانی سوابق مهاجرت"
        )

    subcmd = parts[0].lower()

    if subcmd == "analyze":
        if len(parts) < 2:
            return "❌ لطفاً مسیر پوشه مبدأ را وارد کنید: `/migrate analyze <path>`"
        path = parts[1]
        res = migration_analyze_source(path)
        if not res.get("success"):
            return f"❌ {res.get('message_fa', 'خطا در تحلیل مسیر.')}"
        plan = res.get("plan", {})
        counts = plan.get("items_by_type", {})
        counts_str = ", ".join(f"{k}: {v}" for k, v in counts.items()) or "موردی یافت نشد"
        return (
            f"📋 **طرح مهاجرت آماده شد (شناسه: `{plan.get('plan_id')}`):**\n"
            f"- نوع مبدأ: `{plan.get('source_type', '').upper()}`\n"
            f"- کل آیتم‌ها: {plan.get('total_discovered_items')}\n"
            f"- دسته‌بندی: {counts_str}\n"
            f"- حافظه‌های تخمینی: {plan.get('estimated_memories_count')}\n"
            f"- مهارت‌های تخمینی: {plan.get('estimated_skills_count')}\n\n"
            f"💡 برای اجرای واقعی دستور زیر را بزنید:\n"
            f"`/migrate {plan.get('source_type', 'hermes')} {path}`"
        )

    if subcmd in ("hermes", "openclaw", "run"):
        if len(parts) < 2:
            return f"❌ لطفاً مسیر پوشه مبدأ را وارد کنید: `/migrate {subcmd} <path>`"
        path = parts[1]
        is_dry = "--dry" in parts
        stype = subcmd if subcmd in ("hermes", "openclaw") else "auto"
        res = migration_execute(path, source_type=stype, dry_run=is_dry)
        if not res.get("success"):
            return f"❌ {res.get('summary_fa', 'خطا در مهاجرت.')}"
        rep = res.get("report", {})
        dur = rep.get("duration_ms", 0.0)
        return (
            f"✅ **عملیات مهاجرت با موفقیت پایان یافت ({dur:.1f} میلی‌ثانیه):**\n"
            f"- کل آیتم‌های واردشده: {rep.get('total_imported')}\n"
            f"- حافظه‌ها: {rep.get('memories_imported')}\n"
            f"- مهارت‌ها: {rep.get('skills_imported')}\n"
            f"- تنظیمات: {rep.get('configs_imported')}\n"
            f"- نرمال‌سازی اصطلاحات فارسی: {rep.get('persian_terms_normalized')} مورد\n\n"
            f"{rep.get('summary_fa', '')}"
        )

    if subcmd == "report":
        res = migration_export_report()
        return res.get("markdown_report", "")

    if subcmd == "status":
        res = migration_get_status()
        total = res.get("total_migrations_executed", 0)
        return f"📊 **وضعیت سیستم مهاجرت:**\n- مجموع عملیات‌های انجام‌شده: {total}"

    if subcmd == "reset":
        res = migration_reset()
        return f"✅ {res.get('message_fa', 'بازنشانی شد.')}"

    return "❌ زیردستور نامعتبر است. برای راهنما `/migrate` را ارسال کنید."
