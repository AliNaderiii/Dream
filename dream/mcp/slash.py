"""Slash command handler for MCP (Model Context Protocol) management."""

from __future__ import annotations

from collections.abc import Callable

from dream.mcp.tools import _run_async, get_mcp_manager


def handle_mcp_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/mcp` slash commands.

    Usage:
        /mcp
        /mcp list
        /mcp add <name> <stdio|sse> <cmd_or_url> [args...]
        /mcp remove <server_id>
        /mcp enable <server_id>
        /mcp disable <server_id>
        /mcp tools [server_id]
        /mcp ping <server_id>
        /mcp reload [server_id]
    """
    parts = args.strip().split()
    mgr = get_mcp_manager()

    if not parts or parts[0] in ("list", "status"):
        servers = mgr.list_servers()
        if not servers:
            output(
                "📡 **هیچ سرور MCP پیکربندی نشده است.**\n"
                "برای افزودن: `/mcp add <name> <stdio|sse> <cmd/url>`"
            )
            return True

        output("📡 **سرورهای پروتکل کانتکست مدل (MCP Servers):**\n")
        for s in servers:
            icon = "🟢" if s.get("is_connected") else ("⚪" if s.get("enabled") else "🔴")
            sid = s.get("id", "")
            name = s.get("name", "")
            stype = s.get("type", "")
            status = s.get("status", "")
            cmd_or_url = s.get("command") or s.get("url") or ""
            output(
                f"  {icon} **{name}** (`{sid}`) [{stype}] — وضعیت: {status}\n"
                f"     مسیر/آدرس: `{cmd_or_url}`\n"
            )
        return True

    action = parts[0].lower()

    if action == "add" and len(parts) >= 4:
        name = parts[1]
        stype = parts[2].lower()
        target = parts[3]
        extra_args = parts[4:] if len(parts) > 4 else []

        if stype not in ("stdio", "sse", "ws"):
            output("❌ نوع سرور نامعتبر است. فقط `stdio` یا `sse` یا `ws` مجاز است.")
            return True

        cfg = mgr.add_server(
            name=name,
            type=stype,
            command=target if stype == "stdio" else None,
            args=extra_args if stype == "stdio" else [],
            url=target if stype in ("sse", "ws") else None,
        )
        output(f"✅ سرور MCP با موفقیت افزوده شد: **{name}** (`{cfg.id}`)")
        return True

    if action == "remove" and len(parts) > 1:
        sid = parts[1]
        ok = mgr.remove_server(sid)
        if ok:
            output(f"🗑️ سرور MCP با شناسه `{sid}` حذف شد.")
        else:
            output(f"❌ سرور با شناسه `{sid}` یافت نشد.")
        return True

    if action == "enable" and len(parts) > 1:
        sid = parts[1]
        cfg = mgr.toggle_server(sid, enabled=True)
        if cfg:
            output(f"🟢 سرور MCP `{cfg.name}` فعال شد.")
        else:
            output(f"❌ سرور `{sid}` یافت نشد.")
        return True

    if action == "disable" and len(parts) > 1:
        sid = parts[1]
        cfg = mgr.toggle_server(sid, enabled=False)
        if cfg:
            output(f"🔴 سرور MCP `{cfg.name}` غیرفعال شد.")
        else:
            output(f"❌ سرور `{sid}` یافت نشد.")
        return True

    if action == "tools":
        sid = parts[1] if len(parts) > 1 else None

        async def _get_tools():
            if sid:
                client = await mgr.ensure_connected(sid)
                return await client.list_tools()
            return await mgr.list_all_tools()

        try:
            tools = _run_async(_get_tools())
            if not tools:
                output("ℹ️ هیچ ابزاری یافت نشد.")
                return True
            output(f"🛠️ **ابزارهای MCP کشف‌شده ({len(tools)} ابزار):**\n")
            for t in tools:
                server_tag = f"[{t.server_name or t.server_id}]" if t.server_id else ""
                output(f"  • **{t.name}** {server_tag}: {t.description or 'بدون توضیح'}\n")
            return True
        except Exception as exc:
            output(f"❌ خطا در استعلام ابزارها: {exc}")
            return True

    if action == "ping" and len(parts) > 1:
        sid = parts[1]

        async def _ping():
            return await mgr.test_connection(sid)

        try:
            res = _run_async(_ping())
            if res.get("ok"):
                output(
                    f"⚡ **اتصال برقرار است!**\n"
                    f"  سرور: {res.get('name')}\n"
                    f"  تأخیر (Latency): {res.get('latency_ms')}ms\n"
                    f"  تعداد ابزارها: {res.get('tools_count')}\n"
                    f"  تعداد منابع: {res.get('resources_count')}"
                )
            else:
                output(f"❌ خطا در برقراری اتصال به سرور `{sid}`: {res.get('error')}")
            return True
        except Exception as exc:
            output(f"❌ خطا در پینگ: {exc}")
            return True

    if action == "reload":
        sid = parts[1] if len(parts) > 1 else ""

        async def _reload():
            if sid:
                cfg = mgr._servers.get(sid)
                if not cfg:
                    return {"ok": False, "error": "Server not found"}
                if sid in mgr._clients:
                    await mgr._clients[sid].disconnect()
                    del mgr._clients[sid]
                return await mgr.test_connection(cfg)
            else:
                results = []
                for s_id, cfg in list(mgr._servers.items()):
                    if s_id in mgr._clients:
                        await mgr._clients[s_id].disconnect()
                        del mgr._clients[s_id]
                    if cfg.enabled:
                        res = await mgr.test_connection(cfg)
                        results.append(res)
                return {"ok": True, "count": len(results)}

        try:
            res = _run_async(_reload())
            output(f"🔄 **بارگذاری مجدد سرورها انجام شد.**\nنتیجه: {res}")
            return True
        except Exception as exc:
            output(f"❌ خطا در بارگذاری مجدد: {exc}")
            return True

    output(
        "راهنمای دستورات MCP / MCP Command Help:\n"
        "  /mcp\n"
        "  /mcp list\n"
        "  /mcp add <name> <stdio|sse> <cmd/url> [args...]\n"
        "  /mcp remove <server_id>\n"
        "  /mcp enable <server_id>\n"
        "  /mcp disable <server_id>\n"
        "  /mcp tools [server_id]\n"
        "  /mcp ping <server_id>\n"
        "  /mcp reload [server_id]"
    )
    return True
