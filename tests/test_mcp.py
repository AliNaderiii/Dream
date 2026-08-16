"""Tests for Dream's Model Context Protocol (MCP) Client & Server Manager."""

import asyncio

from dream.mcp.client import MCPClient
from dream.mcp.manager import MCPServerManager
from dream.mcp.models import MCPServerConfig
from dream.mcp.transport import InMemoryTransport


def _run(coro):
    return asyncio.run(coro)


def test_mcp_client_with_in_memory_transport():
    async def _test():
        config = MCPServerConfig(id="test_server", name="TestServer", type="stdio")
        transport = InMemoryTransport(config)
        transport.register_tool(
            "weather",
            "Get current weather",
            {"type": "object", "properties": {"city": {"type": "string"}}},
            lambda city: f"Sunny in {city}",
        )
        transport.register_resource(
            "doc://readme", "Readme", "Project documentation", "# Readme content"
        )

        client = MCPClient(config, transport=transport)
        assert await client.connect() is True
        assert client.is_connected is True

        # List tools
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "weather"
        assert tools[0].description == "Get current weather"

        # Call tool
        result = await client.call_tool("weather", {"city": "Tehran"})
        assert result == "Sunny in Tehran"

        # List resources
        resources = await client.list_resources()
        assert len(resources) == 1
        assert resources[0].uri == "doc://readme"

        # Read resource
        content = await client.read_resource("doc://readme")
        assert content == "# Readme content"

        await client.disconnect()
        assert client.is_connected is False

    _run(_test())


def test_mcp_server_manager_lifecycle(tmp_path):
    async def _test():
        config_file = str(tmp_path / "mcp_servers.json")
        mgr = MCPServerManager(config_path=config_file)

        cfg = mgr.add_server(
            name="Local Tools",
            type="stdio",
            command="python",
            args=["-m", "tools_server"],
        )
        assert cfg.id.startswith("mcp_")
        assert cfg.name == "Local Tools"

        servers = mgr.list_servers()
        assert len(servers) == 1
        assert servers[0]["name"] == "Local Tools"

        # Toggle tool
        assert mgr.toggle_tool(cfg.id, "delete_db", enabled=False) is True
        updated_cfg = mgr._servers[cfg.id]
        assert "delete_db" in updated_cfg.disabled_tools

        # Toggle server
        mgr.toggle_server(cfg.id, enabled=False)
        assert mgr._servers[cfg.id].enabled is False

        # Remove server
        assert mgr.remove_server(cfg.id) is True
        assert len(mgr.list_servers()) == 0

    _run(_test())
