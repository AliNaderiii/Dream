"""CLI and slash command handlers for Multi-Agent Debate & Fact-Checking."""

from __future__ import annotations

from dream.debate.tools import (
    debate_list_sessions,
    debate_reach_consensus,
    debate_reset_all,
    debate_run_autonomous,
    debate_verify_statement,
)


def handle_debate_slash_command(command_str: str) -> str:
    """Handle /debate and /verify slash commands for CLI and REPL.

    Usage:
        /debate <topic>
        /debate list
        /debate status <debate_id>
        /debate reset
        /verify <statement>
    """
    cmd = command_str.strip()

    if cmd.startswith("/verify"):
        statement = cmd[len("/verify") :].strip()
        if not statement:
            return "❌ لطفاً گزاره یا ادعا را برای راستی‌آزمایی وارد کنید."
        res = debate_verify_statement(statement)
        status = res.get("verification_status", "unverified")
        conf = res.get("confidence", 0.0)
        fallacies = res.get("fallacies", [])

        out = [
            "🔎 نتیجه ارزیابی گزاره:",
            f"- وضعیت: `{status}`",
            f"- ضریب اطمینان: {conf:.2f}",
        ]
        if fallacies:
            flist = ", ".join(fallacies)
            out.append(f"- ⚠️ مغالطات شناسایی‌شده: {flist}")
        else:
            out.append("- ✅ هیچ مغالطه منطقی شناسایی نشد.")
        return "\n".join(out)

    if not cmd.startswith("/debate"):
        return "❌ دستور نامعتبر است."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        return (
            "🏛 دستورات مناظره چند-عامل (Debate):\n"
            "  /debate <topic>                           اجرای مناظره خودکار پیرامون موضوع\n"
            "  /debate list                              فهرست مناظرات ثبت‌شده\n"
            "  /debate status <id>                       ارزیابی اجماع نشست\n"
            "  /debate reset                             پاکسازی حافظه مناظرات\n"
            "  /verify <claim>                           راستی‌آزمایی و کشف مغالطات"
        )

    subcmd = parts[1].lower()
    arg_rest = parts[2] if len(parts) > 2 else ""

    if subcmd == "list":
        res = debate_list_sessions()
        debates = res.get("debates", [])
        if not debates:
            return "📜 هیچ مناظره‌ای ثبت نشده است."
        lines = ["🏛 فهرست نشست‌های مناظره:"]
        for d in debates:
            did = d["debate_id"]
            dtop = d["topic"]
            dst = d["status"]
            dcf = d["confidence_score"]
            lines.append(f"- `{did}`: **{dtop}** ({dst}, اطمینان: {dcf})")
        return "\n".join(lines)

    if subcmd == "reset":
        debate_reset_all()
        return "✅ حافظه مناظرات پاکسازی شد."

    if subcmd == "status":
        did = arg_rest.strip()
        if not did:
            return "❌ لطفاً شناسه مناظره را وارد کنید."
        res = debate_reach_consensus(did)
        if not res.get("success"):
            return f"❌ {res.get('error')}"
        return res.get("summary", "")

    # Treat whole arg as topic for autonomous debate
    topic = cmd[len("/debate") :].strip()
    res = debate_run_autonomous(
        topic=topic,
        proponent_arg=f"دلایل موافق پیرامون {topic}",
        opponent_arg=f"دلایل منتقد و چالش‌های {topic}",
    )
    if res.get("success"):
        return res.get("consensus_summary", "")
    return f"❌ خطا در اجرای مناظره: {res.get('error')}"
