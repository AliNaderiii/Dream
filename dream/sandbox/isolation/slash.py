"""CLI and slash command handlers for Sandbox Isolation and WASM Virtualization."""

from __future__ import annotations

from dream.sandbox.isolation.tools import (
    sandbox_export_security_report,
    sandbox_isolate_execute,
    sandbox_reset_isolation,
    sandbox_wasm_execute,
)


def handle_isolation_slash_command(command_str: str) -> str:
    """Handle /isolate, /wasm, and /sandbox_security CLI slash commands.

    Usage:
        /isolate <code>
        /wasm <code_or_expression>
        /sandbox_security [reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/isolate"):
        code = cmd[len("/isolate") :].strip()
        if not code:
            return "❌ لطفاً کد را برای اجرای ایزوله وارد کنید."
        res = sandbox_isolate_execute(code)
        r = res.get("result", {})
        if not r.get("success"):
            v_str = ", ".join(r.get("security_violations", []))
            s_str = ", ".join(r.get("syscalls_blocked", []))
            return (
                "⛔ اجرا به دلیل نقض سیاست امنیتی مسدود شد:\n"
                f"- موارد نقض: {v_str}\n"
                f"- سیس‌کال‌ها: {s_str}"
            )
        dur = r.get("duration_ms", 0.0)
        return f"🛡️ اجرای ایزوله موفق ({dur:.1f} میلی‌ثانیه):\n```\n{r.get('stdout')}\n```"

    if cmd.startswith("/wasm"):
        expr = cmd[len("/wasm") :].strip()
        if not expr:
            return "❌ لطفاً عبارت یا کد محاسباتی را وارد کنید."
        res = sandbox_wasm_execute(expr)
        r = res.get("result", {})
        if not r.get("success"):
            return f"❌ خطا در محاسبه WASM:\n{r.get('stderr')}"
        dur = r.get("duration_ms", 0.0)
        return (
            f"⚡ نتیجه محاسبه در مایکرو‌ران‌تایم WASM ({dur:.2f} میلی‌ثانیه):\n"
            f"```\n{r.get('stdout')}\n```"
        )

    if cmd.startswith("/sandbox_security"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            sandbox_reset_isolation()
            return "✅ آمار ایزولاسیون سندباکس بازنشانی شد."

        res = sandbox_export_security_report()
        return res.get("markdown_report", "")

    return "❌ دستور نامعتبر است."
