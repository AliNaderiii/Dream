"""CLI and slash command handlers for Code Intelligence & AST Refactor."""

from __future__ import annotations

from dream.refactor.tools import (
    refactor_apply_patch,
    refactor_find_symbol,
    refactor_get_status,
    refactor_index_symbols,
    refactor_reset,
    refactor_rollback_patch,
)


def handle_refactor_slash_command(command_str: str) -> str:
    """Handle /refactor CLI slash commands for code intelligence and refactoring.

    Usage:
        /refactor index [dir]
        /refactor find [symbol]
        /refactor apply [plan_id]
        /refactor rollback [plan_id]
        /refactor status
        /refactor reset
    """
    cmd = command_str.strip()
    if not cmd.startswith("/refactor"):
        return "❌ دستور نامعتبر است."

    parts = cmd[len("/refactor") :].strip().split()
    if not parts:
        return (
            "🛠️ **راهنمای دستورات هوشمندی کد و بازآرایی AST (/refactor):**\n"
            "- `/refactor index [dir]`: تحلیل و ایندکس ساختاری نمادهای کد (توابع، کلاس‌ها)\n"
            "- `/refactor find [name]`: جستجوی سریع محل تعریف توابع و متدها\n"
            "- `/refactor apply [plan_id]`: اعمال قطعی و اتمیک تغییرات طرح بازآرایی\n"
            "- `/refactor rollback [plan_id]`: بازگردانی فایل‌ها به وضعیت قبل از بازآرایی\n"
            "- `/refactor status`: مشاهده آمار نمادهای ایندکس‌شده و طرح‌ها\n"
            "- `/refactor reset`: بازنشانی و پاکسازی ایندکس کدی"
        )

    subcmd = parts[0].lower()

    if subcmd == "index":
        target_dir = parts[1] if len(parts) > 1 else "."
        res = refactor_index_symbols(target_dir)
        if not res.get("success"):
            return f"❌ خطا در ایندکس کدی: {res.get('error')}"
        return f"✅ {res.get('summary_fa', 'ایندکس شد.')}"

    if subcmd == "find":
        if len(parts) < 2:
            return "❌ لطفا نام تابع یا کلاس مورد نظر را وارد کنید: `/refactor find [name]`"
        query = parts[1]
        res = refactor_find_symbol(query)
        syms = res.get("symbols", [])
        if not syms:
            return f"🔍 نمادی با نام `{query}` یافت نشد."
        lines = [f"🔍 **نتایج جستجوی نماد `{query}` ({len(syms)} مورد):**"]
        for s in syms:
            lines.append(
                f"- **{s['name']}** (`{s['symbol_type']}`) در `{s['file_path']}:{s['line_start']}`"
            )
            if s.get("signature"):
                lines.append(f"  ↳ امضا: `{s['signature']}`")
        return "\n".join(lines)

    if subcmd == "apply":
        if len(parts) < 2:
            return "❌ شناسه طرح را وارد کنید: `/refactor apply [plan_id]`"
        plan_id = parts[1]
        res = refactor_apply_patch(plan_id)
        if not res.get("success"):
            return f"❌ {res.get('summary_fa', 'خطا در اعمال بازآرایی.')}"
        return f"✅ {res.get('summary_fa', 'اعمال شد.')}"

    if subcmd == "rollback":
        if len(parts) < 2:
            return "❌ شناسه طرح را وارد کنید: `/refactor rollback [plan_id]`"
        plan_id = parts[1]
        res = refactor_rollback_patch(plan_id)
        if not res.get("success"):
            return f"❌ خطا در بازگردانی: {res.get('error')}"
        return f"↩️ {res.get('message_fa', 'بازگردانی شد.')}"

    if subcmd == "status":
        res = refactor_get_status()
        return (
            f"📊 **وضعیت سیستم بازآرایی کد (Refactor Studio):**\n"
            f"- طرح‌های ایجادشده: {res.get('total_plans')}\n"
            f"- گزارش‌های ثبت‌شده: {res.get('total_reports')}"
        )

    if subcmd == "reset":
        res = refactor_reset()
        return f"✅ {res.get('message_fa', 'بازنشانی شد.')}"

    return "❌ دستور نامعتبر است. برای راهنما `/refactor` را وارد کنید."
