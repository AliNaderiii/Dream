"""Agent tool implementations for Model Context Protocol (MCP) discovery and execution."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from dream.mcp.manager import MCPServerManager
from dream.tools.base import tool

logger = logging.getLogger(__name__)

_GLOBAL_MCP_MANAGER: MCPServerManager | None = None


def get_mcp_manager() -> MCPServerManager:
    """Retrieve or initialize singleton MCPServerManager."""
    global _GLOBAL_MCP_MANAGER
    if _GLOBAL_MCP_MANAGER is None:
        _GLOBAL_MCP_MANAGER = MCPServerManager()
    return _GLOBAL_MCP_MANAGER


def reset_mcp_manager() -> None:
    """Reset global MCPServerManager instance for testing and isolation."""
    global _GLOBAL_MCP_MANAGER
    _GLOBAL_MCP_MANAGER = None


def _run_async(coro: Any) -> Any:
    """Helper to run async MCP operations synchronously for tool dispatch."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running inside an event loop: submit to worker thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30.0)
    else:
        return asyncio.run(coro)


@tool(risk="safe")
def mcp_list_servers() -> str:
    """List configured Model Context Protocol (MCP) servers and their live statuses."""
    mgr = get_mcp_manager()
    servers = mgr.list_servers()
    return json.dumps({"servers": servers}, ensure_ascii=False, indent=2)


@tool(risk="safe")
def mcp_list_tools(server_id: str = "") -> str:
    """Discover tools available across all connected MCP servers or a specific server.

    :param server_id: Optional specific MCP server ID to filter tools.
    """
    mgr = get_mcp_manager()

    async def _async_list():
        if server_id:
            client = await mgr.ensure_connected(server_id)
            tools = await client.list_tools()
        else:
            tools = await mgr.list_all_tools()
        return [t.to_dict() for t in tools]

    try:
        tools_data = _run_async(_async_list())
        return json.dumps(
            {"tools": tools_data, "count": len(tools_data)},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        logger.error(f"Failed to list MCP tools: {exc}")
        return json.dumps({"error": f"خطا در دریافت ابزارهای MCP: {exc}"}, ensure_ascii=False)


@tool(risk="guarded")
def mcp_call_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    server_id: str = "",
) -> str:
    """Invoke an MCP tool on a connected server with arguments.

    :param tool_name: Name of the MCP tool to execute.
    :param arguments: Key-value dictionary of arguments for the tool.
    :param server_id: Optional target MCP server ID.
    """
    mgr = get_mcp_manager()
    args = arguments or {}

    async def _async_call():
        return await mgr.call_tool(tool_name, args, server_id=server_id or None)

    try:
        result = _run_async(_async_call())
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return str(result)
    except Exception as exc:
        logger.error(f"Failed to call MCP tool '{tool_name}': {exc}")
        return json.dumps(
            {"error": f"خطا در اجرای ابزار MCP '{tool_name}': {exc}"},
            ensure_ascii=False,
        )


@tool(risk="safe")
def mcp_read_resource(uri: str, server_id: str = "") -> str:
    """Read contents of a resource exposed by an MCP server.

    :param uri: URI of the resource to read.
    :param server_id: Optional target MCP server ID.
    """
    mgr = get_mcp_manager()

    async def _async_read():
        return await mgr.read_resource(uri, server_id=server_id or None)

    try:
        return _run_async(_async_read())
    except Exception as exc:
        logger.error(f"Failed to read MCP resource '{uri}': {exc}")
        return json.dumps(
            {"error": f"خطا در خواندن منبع MCP '{uri}': {exc}"},
            ensure_ascii=False,
        )


@tool(risk="guarded")
def mcp_reload(server_id: str = "") -> str:
    """Reload connections and refresh tool discovery for MCP servers.

    :param server_id: Optional specific server ID to reload.
    """
    mgr = get_mcp_manager()

    async def _async_reload():
        if server_id:
            cfg = mgr._servers.get(server_id)
            if not cfg:
                return {"ok": False, "error": f"Server '{server_id}' not found"}
            return await mgr.test_connection(server_id)
        else:
            results = []
            for sid, cfg in list(mgr._servers.items()):
                if cfg.enabled:
                    res = await mgr.test_connection(sid)
                    results.append(res)
            return {"ok": True, "reloaded": results}

    try:
        outcome = _run_async(_async_reload())
        return json.dumps(outcome, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.error(f"MCP reload failed: {exc}")
        return json.dumps({"error": f"خطا در بارگذاری مجدد سرورهای MCP: {exc}"}, ensure_ascii=False)
