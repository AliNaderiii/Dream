"""Slash command handlers for Code Interpreter & Sandbox Execution."""

from __future__ import annotations

from typing import Any

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
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u06a9\u062f \u067e\u0627\u06cc\u062a\u0648\u0646 \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u062c\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = sandbox_execute_python(code)
        r = res.get("result", {})
        stdout = r.get("stdout", "").strip()
        stderr = r.get("stderr", "").strip()
        dur = r.get("duration_ms", 0.0)

        out_parts = [f"\u2699\ufe0f \u0646\u062a\u06cc\u062c\u0647 \u0627\u062c\u0631\u0627 ({dur:.1f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647):"]
        if stdout:
            out_parts.append(f"```text\n{stdout}\n```")
        if stderr:
            out_parts.append(f"\u274c \u062e\u0637\u0627:\n```text\n{stderr}\n```")
        if not stdout and not stderr:
            out_parts.append("\u2705 \u06a9\u062f \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0648 \u0628\u062f\u0648\u0646 \u062e\u0631\u0648\u062c\u06cc \u0627\u062c\u0631\u0627 \u0634\u062f.")
        return "\n".join(out_parts)

    if cmd.startswith("/data"):
        data_arg = cmd[len("/data") :].strip()
        if not data_arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u0633\u06cc\u0631 \u0641\u0627\u06cc\u0644 CSV \u06cc\u0627 \u0645\u062d\u062a\u0648\u0627\u06cc \u062f\u0627\u062f\u0647 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = sandbox_analyze_dataset(data_arg)
        if res.get("success"):
            return res.get("markdown_report", "")
        return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u062a\u062d\u0644\u06cc\u0644 \u062f\u0627\u062f\u0647: {res.get('error')}"

    parts = cmd.split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "status"

    if subcommand == "reset":
        sandbox_reset_session()
        return "\u2705 \u0645\u062d\u06cc\u0637 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

    if subcommand == "status":
        st = sandbox_get_status()
        return (
            f"\U0001f4df \u0648\u0636\u0639\u06cc\u062a \u0633\u0646\u062f\u0628\u0627\u06a9\u0633:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u0627\u062c\u0631\u0627\u0647\u0627: {st.get('total_executions')}\n"
            f"- \u0641\u0627\u06cc\u0644\u200c\u0647\u0627\u06cc \u062a\u0648\u0644\u06cc\u062f\u0634\u062f\u0647: {st.get('total_artifacts')}\n"
            f"- \u0645\u062a\u063a\u06cc\u0631\u0647\u0627\u06cc \u0641\u0639\u0627\u0644 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647: {st.get('variables_count')}"
        )

    return (
        "\u2699\ufe0f \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0645\u0641\u0633\u0631 \u06a9\u062f \u0648 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633:\n"
        "  /code <python_code>               \u0627\u062c\u0631\u0627\u06cc \u06a9\u062f \u067e\u0627\u06cc\u062a\u0648\u0646\n"
        "  /data <path_or_csv>               \u062a\u062d\u0644\u06cc\u0644 \u0622\u0645\u0627\u0631\u06cc \u062f\u0627\u062f\u06af\u0627\u0646\n"
        "  /sandbox status                   \u0648\u0636\u0639\u06cc\u062a \u0645\u062d\u06cc\u0637 \u0627\u062c\u0631\u0627\n"
        "  /sandbox reset                    \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0648 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u062d\u0627\u0641\u0638\u0647"
    )
