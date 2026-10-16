"""Slash handlers for the static isolation audit (no execution — MASTER-P0).

The commands still answer, but they say the truth: nothing in this subsystem
runs code, so a benign payload is ``unavailable`` rather than "successful", and
only a static-policy hit is reported as ``blocked``.
"""

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
        if res.get("blocked"):
            v_str = ", ".join(r.get("security_violations", []))
            s_str = ", ".join(r.get("syscalls_blocked", []))
            return (
                "⛔ بازرسی ایستا نقض سیاست امنیتی را تشخیص داد:\n"
                f"- موارد نقض: {v_str}\n"
                f"- سیس‌کال‌ها: {s_str}"
            )
        return (
            "ℹ️ این زیرسیستم کد اجرا نمی‌کند (fail-closed)؛ فقط بازرسی ایستا انجام شد.\n"
            "برای اجرای واقعی، از اجراکنندهٔ کانتینری سندباکس استفاده کنید."
        )

    if cmd.startswith("/wasm"):
        expr = cmd[len("/wasm") :].strip()
        if not expr:
            return "❌ لطفاً عبارت یا کد محاسباتی را وارد کنید."
        res = sandbox_wasm_execute(expr)
        r = res.get("result", {})
        if res.get("blocked"):
            return f"⛔ بازرسی ایستا اجرای این محتوا را ممنوع کرد:\n{r.get('stderr')}"
        return (
            "ℹ️ مایکرو‌ران‌تایم WASM غیرفعال است و کدی اجرا نمی‌کند (fail-closed).\n"
            f"{r.get('stderr')}"
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
