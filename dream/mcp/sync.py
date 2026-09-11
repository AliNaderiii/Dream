"""Dynamic synchronization bridging MCP tools to Dream's global tool registry."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.mcp.manager import MCPServerManager
from dream.mcp.models import MCPTool
from dream.tools.base import REGISTRY, Tool

logger = logging.getLogger(__name__)


def create_dynamic_mcp_tool_handler(manager: MCPServerManager, mcp_tool: MCPTool):
    """Factory creating a callable handler for an individual MCP tool."""

    def handler(**kwargs: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        async def _call():
            return await manager.call_tool(
                mcp_tool.name, arguments=kwargs, server_id=mcp_tool.server_id
            )

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _call()).result(timeout=30.0)
        else:
            return asyncio.run(_call())

    return handler


async def sync_mcp_tools_to_registry(
    manager: MCPServerManager,
    prefix_server_name: bool = False,
) -> int:
    """Discover tools from all enabled MCP servers and register them as native Dream Tools."""
    try:
        tools = await manager.list_all_tools()
    except Exception as exc:
        logger.error(f"Failed to fetch MCP tools during registry sync: {exc}")
        return 0

    registered_count = 0
    for t in tools:
        if not t.enabled:
            continue

        tool_name = f"{t.server_name}_{t.name}" if prefix_server_name and t.server_name else t.name
        # Sanitize tool name for schema compliance
        clean_name = tool_name.replace("-", "_").replace(" ", "_")

        dream_tool = Tool(
            name=clean_name,
            function=create_dynamic_mcp_tool_handler(manager, t),
            description=t.description or f"MCP tool '{t.name}' from server '{t.server_name}'",
            schema=t.input_schema or {"type": "object", "properties": {}},
            risk=t.risk or "guarded",
        )
        REGISTRY[clean_name] = dream_tool
        registered_count += 1
        logger.info(f"Registered dynamic MCP tool '{clean_name}' into Dream REGISTRY.")

    return registered_count
