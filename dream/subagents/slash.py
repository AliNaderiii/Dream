"""Slash command handler for interactive subagent inspection, launching, and control."""

from __future__ import annotations

from collections.abc import Callable

from dream.subagents.coordinator import BUILTIN_ROLES
from dream.subagents.tools import _run_async, get_subagent_manager


def handle_subagent_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/subagent` or `/subagents` slash commands.

    Usage:
        /subagents
        /subagent list
        /subagent roles
        /subagent spawn <role> <prompt...>
        /subagent wait <id>
        /subagent stop <id>
        /subagent logs <id>
    """
    parts = args.strip().split()
    mgr = get_subagent_manager()

    if not parts or parts[0].lower() in ("list", "status"):
        agents = mgr.list()
        if not agents:
            output(
                "🤖 **هیچ زیرایجنت فعالی در حافظه وجود ندارد.**\n"
                "برای اجرای ایجنت جدید: `/subagent spawn <role> <task>`"
            )
            return True

        output(f"🤖 **فهرست زیرایجنت‌های سیستم ({len(agents)} ایجنت):**\n")
        for a in agents:
            icon = "🟢" if a.status == "running" else ("✅" if a.status == "completed" else "⚪")
            output(
                f"  {icon} **{a.name}** (`{a.id}`) — وضعیت: {a.status}\n"
                f"     نوبت‌ها: {a.turn_count} | توکن‌ها: {a.token_count:,}\n"
            )
        return True

    action = parts[0].lower()

    if action == "roles":
        output("👥 **نقش‌های پیش‌فرض زیرایجنت‌ها (Built-in Subagent Roles):**\n")
        for name, role in BUILTIN_ROLES.items():
            output(
                f"  • **{name}**: {role.description}\n"
                f"     ابزارها: {', '.join(role.tools)}\n"
            )
        return True

    if action == "spawn" and len(parts) >= 3:
        role_name = parts[1].lower()
        prompt = " ".join(parts[2:])

        role_obj = BUILTIN_ROLES.get(role_name)
        tools = role_obj.tools if role_obj else None
        sys_prompt = role_obj.system_prompt if role_obj else ""

        from dream.subagents.types import SubAgentSpec

        spec = SubAgentSpec(
            prompt=prompt,
            name=f"sub_{role_name}",
            system_prompt=sys_prompt,
            tools=tools,
        )
        agent = mgr.spawn(spec)
        output(f"🚀 زیرایجنت جدید با نقش `{role_name}` ایجاد شد: `{agent.id}`")
        return True

    if action == "wait" and len(parts) > 1:
        aid = parts[1]

        async def _wait():
            return await mgr.wait(aid, timeout=45.0)

        output(f"⏳ در حال انتظار برای تکمیل زیرایجنت `{aid}`...")
        try:
            finished = _run_async(_wait())
            if not finished:
                output(f"❌ زیرایجنت `{aid}` یافت نشد یا زمان انتظار به پایان رسید.")
                return True
            msg_body = finished.result or finished.error
            output(
                f"🏁 **نتیجه زیرایجنت {finished.name} ({finished.status}):**\n\n{msg_body}"
            )
            return True
        except Exception as exc:
            output(f"❌ خطا در انتظار: {exc}")
            return True

    if action == "stop" and len(parts) > 1:
        aid = parts[1]

        async def _cancel():
            return await mgr.cancel(aid)

        try:
            agent = _run_async(_cancel())
            if agent:
                output(f"🛑 زیرایجنت `{aid}` متوقف شد.")
            else:
                output(f"❌ زیرایجنت `{aid}` یافت نشد.")
            return True
        except Exception as exc:
            output(f"❌ خطا در توقف زیرایجنت: {exc}")
            return True

    if action == "logs" and len(parts) > 1:
        aid = parts[1]
        agent = mgr.get(aid)
        if not agent:
            output(f"❌ زیرایجنت `{aid}` یافت نشد.")
            return True
        output(f"📜 **لاگ‌های اجرای زیرایجنت {agent.name}:**\n")
        for entry in agent.log[-10:]:
            output(f"  [{entry.level}] {entry.message}")
        return True

    output(
        "راهنمای دستورات زیرایجنت / Subagent Command Help:\n"
        "  /subagents\n"
        "  /subagent list\n"
        "  /subagent roles\n"
        "  /subagent spawn <role> <task>\n"
        "  /subagent wait <id>\n"
        "  /subagent stop <id>\n"
        "  /subagent logs <id>"
    )
    return True
