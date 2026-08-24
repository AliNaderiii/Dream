"""MCP client for connecting to Model Context Protocol servers."""

from __future__ import annotations

import json
from typing import Any

from .models import MCPPrompt, MCPResource, MCPServerConfig, MCPTool
from .transport import InMemoryTransport, MCPTransport, SSETransport, StdioTransport


class MCPClient:
    """Connects to MCP servers and exposes their tools, resources, and prompts to Dream."""

    def __init__(self, config: MCPServerConfig, transport: MCPTransport | None = None) -> None:
        self.config = config
        if transport:
            self._transport = transport
        elif config.type == "stdio":
            self._transport = StdioTransport(config)
        elif config.type in ("sse", "ws"):
            self._transport = SSETransport(config)
        else:
            self._transport = InMemoryTransport(config)

    @property
    def is_connected(self) -> bool:
        return self._transport.is_connected

    async def connect(self, server_config: MCPServerConfig | None = None) -> bool:
        """Connect to the MCP server."""
        if server_config:
            self.config = server_config
        return await self._transport.connect()

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        await self._transport.close()

    async def list_tools(self) -> list[MCPTool]:
        """Fetch available tools from the server."""
        res = await self._transport.send_request("tools/list", {})
        raw_tools = res.get("tools", []) if isinstance(res, dict) else []
        tools: list[MCPTool] = []
        for item in raw_tools:
            if isinstance(item, dict):
                t = MCPTool.from_dict(item, server_id=self.config.id, server_name=self.config.name)
                t.enabled = t.name not in self.config.disabled_tools
                tools.append(t)
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Execute a tool on the MCP server."""
        params = {"name": tool_name, "arguments": arguments or {}}
        res = await self._transport.send_request("tools/call", params)
        if isinstance(res, dict):
            # Extract content from MCP format
            contents = res.get("content", [])
            if contents and isinstance(contents, list):
                text_parts = [
                    c.get("text", "")
                    for c in contents
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                if text_parts:
                    joined = "\n".join(text_parts)
                    try:
                        return json.loads(joined)
                    except Exception:
                        from dream.security.injection import guard_untrusted

                        # L5 (SEC Stage D): MCP payload text is untrusted and
                        # crosses into context only scanned.
                        return guard_untrusted(joined, source=f"mcp:{self.config.name}")
            return res
        return res

    async def list_resources(self) -> list[MCPResource]:
        """Fetch available resources from the server."""
        res = await self._transport.send_request("resources/list", {})
        raw_resources = res.get("resources", []) if isinstance(res, dict) else []
        return [
            MCPResource.from_dict(item, server_id=self.config.id)
            for item in raw_resources
            if isinstance(item, dict)
        ]

    async def read_resource(self, uri: str) -> str:
        """Read resource content by URI."""
        res = await self._transport.send_request("resources/read", {"uri": uri})
        if isinstance(res, dict):
            contents = res.get("contents", [])
            if contents and isinstance(contents, list):
                first = contents[0]
                if isinstance(first, dict):
                    text = str(first.get("text") or first.get("blob") or "")
                    from dream.security.injection import guard_untrusted

                    return guard_untrusted(text, source=f"mcp:{self.config.name}")
        return str(res)

    async def list_prompts(self) -> list[MCPPrompt]:
        """Fetch available prompt templates from the server."""
        res = await self._transport.send_request("prompts/list", {})
        raw_prompts = res.get("prompts", []) if isinstance(res, dict) else []
        return [
            MCPPrompt.from_dict(item, server_id=self.config.id)
            for item in raw_prompts
            if isinstance(item, dict)
        ]

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Retrieve a formatted prompt."""
        params = {"name": name, "arguments": arguments or {}}
        return await self._transport.send_request("prompts/get", params)
