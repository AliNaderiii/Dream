"""Slash command handlers for Code Interpreter & Sandbox Execution."""

from __future__ import annotations

from dream.sandbox.tools import (
    sandbox_analyze_dataset,
    sandbox_execute_python,
    sandbox_get_status,
    sandbox_reset_session,
)


def handle_sandbox_slash_command(command_str: str) -> str:
    """Handle /code, /data, and /sandbox CLI slash commands.

    Usage:
        /code <python_snippet>
        /data <path_or_content>
        /sandbox reset
        /sandbox status
    """
    cmd = command_str.strip()

    if cmd.startswith("/code"):
        code = cmd[len("/code") :].strip()
        if not code:
            return "❌ لطفاً کد پایتون را برای اجرا وارد کنید."
        res = sandbox_execute_python(code)
        r = res.get("result", {})
        stdout = r.get("stdout", "").strip()
        stderr = r.get("stderr", "").strip()
        dur = r.get("duration_ms", 0.0)

        out_parts = [f"⚙️ نتیجه اجرا ({dur:.1f} میلی‌ثانیه):"]
        if stdout:
            out_parts.append(f"```text\n{stdout}\n```")
        if stderr:
            out_parts.append(f"❌ خطا:\n```text\n{stderr}\n```")
        if not stdout and not stderr:
            out_parts.append("✅ کد با موفقیت و بدون خروجی اجرا شد.")
        return "\n".join(out_parts)

    if cmd.startswith("/data"):
        data_arg = cmd[len("/data") :].strip()
        if not data_arg:
            return "❌ لطفاً مسیر فایل CSV یا محتوای داده را وارد کنید."
        res = sandbox_analyze_dataset(data_arg)
        if res.get("success"):
            return res.get("markdown_report", "")
        return f"❌ خطا در تحلیل داده: {res.get('error')}"

    parts = cmd.split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "status"

    if subcommand == "reset":
        sandbox_reset_session()
        return "✅ محیط سندباکس با موفقیت بازنشانی شد."

    if subcommand == "status":
        st = sandbox_get_status()
        return (
            "🗟 وضعیت سندباکس:\n"
            f"- تعداد اجراها: {st.get('total_executions')}\n"
            f"- فایل‌های تولیدشده: {st.get('total_artifacts')}\n"
            f"- متغیرهای فعال در حافظه: {st.get('variables_count')}"
        )

    return (
        "⚙️ دستورات مفسر کد و سندباکس:\n"
        "  /code <python_code>               اجرای کد پایتون\n"
        "  /data <path_or_csv>               تحلیل آماری دادگان\n"
        "  /sandbox status                   وضعیت محیط اجرا\n"
        "  /sandbox reset                    پاکسازی و بازنشانی حافظه"
    )
