"""MCP server manager for multi-server lifecycle, tool discovery, and configuration persistence."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from typing import Any

from .client import MCPClient
from .models import MCPResource, MCPServerConfig, MCPTool


class MCPServerManager:
    """Manages MCP server configurations, active client connections, and tool aggregation."""

    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = config_path or os.environ.get(
            "DREAM_MCP_SERVERS_PATH", "data/mcp_servers.json"
        )
        self._lock = threading.RLock()
        self._servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "id" in item:
                            cfg = MCPServerConfig.from_dict(item)
                            self._servers[cfg.id] = cfg
        except Exception:
            pass

    def _save_configs(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                data = [s.to_dict() for s in self._servers.values()]
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def add_server(
        self,
        name: str,
        type: str,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
        server_id: str | None = None,
    ) -> MCPServerConfig:
        """Add and persist a new MCP server configuration."""
        sid = server_id or f"mcp_{uuid.uuid4().hex[:12]}"
        cfg = MCPServerConfig(
            id=sid,
            name=name,
            type=type,  # type: ignore
            command=command,
            args=args or [],
            env=env or {},
            url=url,
            headers=headers or {},
            enabled=enabled,
        )
        with self._lock:
            self._servers[sid] = cfg
            self._save_configs()
        return cfg

    def remove_server(self, server_id: str) -> bool:
        """Remove a server and disconnect its client."""
        with self._lock:
            cfg = self._servers.pop(server_id, None)
            client = self._clients.pop(server_id, None)
            self._save_configs()

        if client and client.is_connected:
            try:
                asyncio.create_task(client.disconnect())
            except Exception:
                pass
        return cfg is not None

    def toggle_server(self, server_id: str, enabled: bool) -> MCPServerConfig | None:
        """Enable or disable a server."""
        with self._lock:
            cfg = self._servers.get(server_id)
            if not cfg:
                return None
            cfg.enabled = enabled
            self._save_configs()
            if not enabled and server_id in self._clients:
                client = self._clients.pop(server_id)
                try:
                    asyncio.create_task(client.disconnect())
                except Exception:
                    pass
            return cfg

    def toggle_tool(self, server_id: str, tool_name: str, enabled: bool) -> bool:
        """Enable or disable an individual tool on an MCP server."""
        with self._lock:
            cfg = self._servers.get(server_id)
            if not cfg:
                return False
            if enabled and tool_name in cfg.disabled_tools:
                cfg.disabled_tools.remove(tool_name)
            elif not enabled and tool_name not in cfg.disabled_tools:
                cfg.disabled_tools.append(tool_name)
            self._save_configs()
            return True

    def get_client(self, server_id: str) -> MCPClient | None:
        """Get or instantiate an active client for the server."""
        with self._lock:
            cfg = self._servers.get(server_id)
            if not cfg:
                return None
            if server_id in self._clients:
                return self._clients[server_id]
            client = MCPClient(cfg)
            self._clients[server_id] = client
            return client

    def register_client(self, server_id: str, client: MCPClient) -> None:
        """Register an existing client (useful for mocks/tests)."""
        with self._lock:
            self._servers[server_id] = client.config
            self._clients[server_id] = client
            self._save_configs()

    async def ensure_connected(self, server_id: str) -> MCPClient:
        """Ensure client is connected and return it."""
        client = self.get_client(server_id)
        if not client:
            raise ValueError(f"No server found with id {server_id}")
        if not client.is_connected:
            await client.connect()
        return client

    async def test_connection(self, server_id_or_config: str | MCPServerConfig) -> dict[str, Any]:
        """Test connection to an MCP server and report tool/resource counts."""
        started = time.monotonic()
        if isinstance(server_id_or_config, str):
            cfg = self._servers.get(server_id_or_config)
            if not cfg:
                return {"ok": False, "error": f"Server {server_id_or_config} not found"}
        else:
            cfg = server_id_or_config

        temp_client = MCPClient(cfg)
        try:
            await asyncio.wait_for(temp_client.connect(), timeout=15.0)
            tools = await temp_client.list_tools()
            resources = await temp_client.list_resources()
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            await temp_client.disconnect()
            return {
                "ok": True,
                "server_id": cfg.id,
                "name": cfg.name,
                "type": cfg.type,
                "tools_count": len(tools),
                "resources_count": len(resources),
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            return {
                "ok": False,
                "server_id": cfg.id,
                "name": cfg.name,
                "error": str(exc),
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
            }

    async def list_all_tools(self) -> list[MCPTool]:
        """Aggregate all available tools across all enabled MCP servers."""
        all_tools: list[MCPTool] = []
        with self._lock:
            enabled_servers = [s for s in self._servers.values() if s.enabled]

        for s in enabled_servers:
            try:
                client = await self.ensure_connected(s.id)
                tools = await client.list_tools()
                for t in tools:
                    t.enabled = t.name not in s.disabled_tools
                    all_tools.append(t)
            except Exception:
                pass
        return all_tools

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None, server_id: str | None = None
    ) -> Any:
        """Find and execute an MCP tool."""
        if server_id:
            client = await self.ensure_connected(server_id)
            return await client.call_tool(tool_name, arguments)

        # Search across connected servers
        for sid, cfg in self._servers.items():
            if not cfg.enabled or tool_name in cfg.disabled_tools:
                continue
            try:
                client = await self.ensure_connected(sid)
                tools = await client.list_tools()
                if any(t.name == tool_name for t in tools):
                    return await client.call_tool(tool_name, arguments)
            except Exception:
                continue

        raise ValueError(f"MCP tool {tool_name!r} not found on any active server")

    async def list_all_resources(self) -> list[MCPResource]:
        """Aggregate all available resources across all enabled MCP servers."""
        all_resources: list[MCPResource] = []
        with self._lock:
            enabled_servers = [s for s in self._servers.values() if s.enabled]

        for s in enabled_servers:
            try:
                client = await self.ensure_connected(s.id)
                resources = await client.list_resources()
                all_resources.extend(resources)
            except Exception:
                pass
        return all_resources

    async def read_resource(self, uri: str, server_id: str | None = None) -> str:
        """Read resource content by URI across servers."""
        if server_id:
            client = await self.ensure_connected(server_id)
            return await client.read_resource(uri)

        for sid, cfg in self._servers.items():
            if not cfg.enabled:
                continue
            try:
                client = await self.ensure_connected(sid)
                resources = await client.list_resources()
                if any(r.uri == uri for r in resources):
                    return await client.read_resource(uri)
            except Exception:
                continue

        raise ValueError(f"MCP resource {uri!r} not found on any active server")

    def list_servers(self) -> list[dict[str, Any]]:
        """List all configured servers and their current status."""
        with self._lock:
            result = []
            for sid, s in self._servers.items():
                client = self._clients.get(sid)
                connected = client.is_connected if client else False
                status = (
                    "connected" if connected else ("disabled" if not s.enabled else "disconnected")
                )
                result.append(
                    {
                        **s.to_dict(),
                        "status": status,
                        "is_connected": connected,
                    }
                )
            return result
