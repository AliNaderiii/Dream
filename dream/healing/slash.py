"""CLI and slash command handlers for Self-Healing and Telemetry."""

from __future__ import annotations

from dream.healing.tools import (
    healing_diagnose_failure,
    healing_run_chaos_test,
    telemetry_export_report,
    telemetry_reset_all,
)


def handle_healing_slash_command(command_str: str) -> str:
    """Handle /heal, /chaos, and /telemetry CLI slash commands.

    Usage:
        /heal <error_description>
        /chaos <fault_type> [target_name]
        /telemetry [report|reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/heal"):
        err = cmd[len("/heal") :].strip()
        if not err:
            return "❌ لطفاً شرح خطا را برای تشخیص وارد کنید."
        res = healing_diagnose_failure(err)
        rep = res.get("report", {})
        return (
            "🩹 نتیجه تشخیص و خودترمیمی:\n"
            f"- شناسه: `{rep.get('incident_id')}`\n"
            f"- نوع خطا: `{rep.get('fault_type')}`\n"
            f"- اقدام ترمیمی: `{rep.get('action_taken')}`\n"
            f"- زمان بازیابی: {rep.get('recovery_latency_ms', 0.0):.1f} میلی‌ثانیه"
        )

    if cmd.startswith("/chaos"):
        parts = cmd.split()
        fault = parts[1] if len(parts) > 1 else "rate_limit"
        target = parts[2] if len(parts) > 2 else "agent_service"
        res = healing_run_chaos_test(fault_type=fault, target_name=target)
        rep = res.get("report", {})
        return (
            "⚡ آزمایش آشوب (Chaos Test):\n"
            f"- خطای تزریق‌شده: `{rep.get('fault_type')}` روی `{target}`\n"
            f"- پاسخ سیستم: `{rep.get('action_taken')}` (بازیابی موفق ✅)"
        )

    if cmd.startswith("/telemetry"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            telemetry_reset_all()
            return "✅ داده‌های تلمتری بازنشانی شد."

        res = telemetry_export_report()
        return res.get("markdown_report", "")

    return "❌ دستور نامعتبر است."
