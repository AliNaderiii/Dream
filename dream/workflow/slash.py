"""CLI and slash command handlers for Long-Horizon Workflow Subsystem."""

from __future__ import annotations

from dream.workflow.tools import (
    get_global_workflow_engine,
    workflow_approve_step,
    workflow_export_diagram,
    workflow_get_status,
    workflow_reset,
    workflow_rollback,
)


def handle_workflow_slash_command(command_str: str) -> str:
    """Handle /workflow CLI slash commands for workflow orchestration.

    Usage:
        /workflow list
        /workflow run [wf_id]
        /workflow approve [wf_id]
        /workflow rollback [wf_id]
        /workflow diagram [wf_id]
        /workflow status [wf_id]
        /workflow reset
    """
    cmd = command_str.strip()
    if not cmd.startswith("/workflow"):
        return "❌ دستور نامعتبر است."

    parts = cmd[len("/workflow") :].strip().split()
    if not parts:
        return (
            "🔄 **راهنمای دستورات مدیریت گردش‌کار و تراکنش‌های Saga (/workflow):**\n"
            "- `/workflow list`: مشاهده لیست گردش‌کارهای فعال\n"
            "- `/workflow run [id]`: اجرای خودکار تمام مراحل گردش‌کار تا توقف یا اتمام\n"
            "- `/workflow approve [id]`: اعطای تاییدیه انسانی (Human-in-the-Loop) و ادامه اجرا\n"
            "- `/workflow rollback [id]`: بازگردانی تراکنش‌ها با الگوی Saga Compensations\n"
            "- `/workflow diagram [id]`: نمایش گراف و دیاگرام بصری وضعیت مراحل\n"
            "- `/workflow status [id]`: جزئیات تله‌متری و وضعیت متغیرهای زمینه\n"
            "- `/workflow reset`: بازنشانی و پاکسازی گردش‌کارها"
        )

    subcmd = parts[0].lower()
    wf_id = parts[1] if len(parts) > 1 else "wf_demo_financial"

    if subcmd == "list":
        engine = get_global_workflow_engine()
        wfs = engine.list_workflows()
        lines = ["📋 **گردش‌کارهای ثبت‌شده در سیستم:**"]
        for w in wfs:
            lines.append(
                f"- `{w['workflow_id']}`: {w['name']} "
                f"(وضعیت: `{w['status']}` — مرحله {w['current_step']}/{w['total_steps']})"
            )
        return "\n".join(lines)

    if subcmd == "run":
        engine = get_global_workflow_engine()
        try:
            rep = engine.run_all(wf_id)
            return (
                f"🚀 **پایان اجرای گردش‌کار `{wf_id}` ({rep.duration_ms:.1f} میلی‌ثانیه):**\n"
                f"- وضعیت نهایی: `{rep.status.value}`\n"
                f"- مراحل تکمیل‌شده: `{rep.completed_steps}/{rep.total_steps}`\n\n"
                f"{rep.summary_fa}"
            )
        except Exception as exc:
            return f"❌ خطا در اجرای گردش‌کار: {exc}"

    if subcmd == "approve":
        res = workflow_approve_step(wf_id)
        if not res.get("success"):
            return f"❌ خطا در اعطای تاییدیه: {res.get('error')}"
        return f"✅ {res.get('summary_fa', 'تایید شد.')} (مرحله بعدی آماده اجرا است)"

    if subcmd == "rollback":
        res = workflow_rollback(wf_id)
        if not res.get("success"):
            return f"❌ خطا در عملیات بازگشت: {res.get('error')}"
        return f"↩️ {res.get('summary_fa', 'عملیات بازگشت انجام شد.')}"

    if subcmd == "diagram":
        res = workflow_export_diagram(wf_id)
        return res.get("diagram_markdown", "")

    if subcmd == "status":
        res = workflow_get_status(wf_id)
        if not res.get("success"):
            return f"❌ {res.get('error')}"
        wf = res.get("workflow", {})
        return (
            f"📊 **وضعیت گردش‌کار `{wf_id}`:**\n"
            f"- عنوان: **{wf.get('name')}**\n"
            f"- وضعیت: `{wf.get('status')}`\n"
            f"- پیشرفت: `{wf.get('current_step_index')}/{wf.get('total_steps')}` مرحله\n"
            f"- تعداد چک‌پوینت‌های ذخیره‌شده: `{wf.get('checkpoints_count')}`"
        )

    if subcmd == "reset":
        res = workflow_reset()
        return f"✅ {res.get('message_fa', 'بازنشانی شد.')}"

    return "❌ دستور نامعتبر است. برای راهنما `/workflow` را وارد کنید."
