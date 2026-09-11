"""Comprehensive test suite for the Model Context Protocol (MCP) subsystem."""

from __future__ import annotations

import asyncio
import json

from dream.mcp.client import MCPClient
from dream.mcp.manager import MCPServerManager
from dream.mcp.models import MCPServerConfig
from dream.mcp.slash import handle_mcp_command
from dream.mcp.sync import sync_mcp_tools_to_registry
from dream.mcp.tools import (
    get_mcp_manager,
    mcp_call_tool,
    mcp_list_servers,
    mcp_list_tools,
    mcp_read_resource,
    mcp_reload,
    reset_mcp_manager,
)
from dream.mcp.transport import InMemoryTransport
from dream.tools.base import REGISTRY
from dream.tools.toolsets import filter_tools, get_toolset


def create_mock_mcp_client(
    server_id: str = "mock_server",
    name: str = "Mock MCP Server",
) -> MCPClient:
    """Helper to construct an active MCPClient backed by InMemoryTransport."""
    config = MCPServerConfig(id=server_id, name=name, type="stdio")
    transport = InMemoryTransport(config)

    transport.register_tool(
        name="database_query",
        description="Run SQL queries against local SQLite database",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=lambda query: {"rows": [{"id": 1, "val": "dream_data"}], "sql": query},
    )

    transport.register_resource(
        uri="schema://sqlite/main",
        name="Database Schema",
        description="SQLite Database Schema DDL",
        content="CREATE TABLE users (id INT, name TEXT);",
    )

    client = MCPClient(config, transport=transport)
    return client


def test_mcp_manager_crud_and_persistence(tmp_path):
    """Verify MCPServerManager configuration persistence and lifecycle management."""
    cfg_file = tmp_path / "mcp_servers.json"
    mgr = MCPServerManager(config_path=str(cfg_file))

    # Add stdio server
    cfg1 = mgr.add_server(
        name="File Server",
        type="stdio",
        command="python",
        args=["-m", "files"],
    )
    assert cfg1.name == "File Server"
    assert cfg1.enabled is True

    # Add SSE server
    cfg2 = mgr.add_server(
        name="Remote Analytics",
        type="sse",
        url="https://api.example.com/mcp",
    )
    assert cfg2.type == "sse"

    # Verify persistent reloading
    mgr2 = MCPServerManager(config_path=str(cfg_file))
    assert len(mgr2.list_servers()) == 2

    # Toggle enabled
    mgr2.toggle_server(cfg1.id, enabled=False)
    assert mgr2._servers[cfg1.id].enabled is False

    # Remove
    assert mgr2.remove_server(cfg2.id) is True
    assert len(mgr2.list_servers()) == 1


def test_mcp_tools_and_wrappers():
    """Verify agent tools for listing, discovering, and executing MCP operations."""
    reset_mcp_manager()
    mgr = get_mcp_manager()

    client = create_mock_mcp_client(server_id="mock_db", name="Mock Database Server")
    asyncio.run(client.connect())
    mgr.register_client("mock_db", client)

    # Tool: mcp_list_servers
    servers_json = mcp_list_servers()
    servers_data = json.loads(servers_json)
    assert "servers" in servers_data
    assert any(s["id"] == "mock_db" for s in servers_data["servers"])

    # Tool: mcp_list_tools
    tools_json = mcp_list_tools("mock_db")
    tools_data = json.loads(tools_json)
    assert tools_data["count"] == 1
    assert tools_data["tools"][0]["name"] == "database_query"

    # Tool: mcp_call_tool
    call_json = mcp_call_tool(
        "database_query",
        {"query": "SELECT * FROM users;"},
        server_id="mock_db",
    )
    call_data = json.loads(call_json)
    assert "rows" in call_data
    assert call_data["rows"][0]["val"] == "dream_data"

    # Tool: mcp_read_resource
    res_content = mcp_read_resource("schema://sqlite/main", server_id="mock_db")
    assert "CREATE TABLE users" in res_content

    # Tool: mcp_reload
    reload_json = mcp_reload("mock_db")
    reload_data = json.loads(reload_json)
    assert reload_data.get("ok") is True or "tools_count" in reload_data


def test_mcp_slash_commands():
    """Verify `/mcp` interactive slash command processing."""
    reset_mcp_manager()
    mgr = get_mcp_manager()

    client = create_mock_mcp_client(server_id="slash_db", name="Slash Test DB")
    asyncio.run(client.connect())
    mgr.register_client("slash_db", client)

    outputs: list[str] = []

    # /mcp list
    handle_mcp_command("list", output=outputs.append)
    assert any("Slash Test DB" in out for out in outputs)

    # /mcp tools
    outputs.clear()
    handle_mcp_command("tools slash_db", output=outputs.append)
    assert any("database_query" in out for out in outputs)

    # /mcp ping
    outputs.clear()
    handle_mcp_command("ping slash_db", output=outputs.append)
    assert any("اتصال برقرار است" in out or "Latency" in out for out in outputs)

    # /mcp disable and enable
    outputs.clear()
    handle_mcp_command("disable slash_db", output=outputs.append)
    assert any("غیرفعال شد" in out for out in outputs)
    outputs.clear()
    handle_mcp_command("enable slash_db", output=outputs.append)
    assert any("فعال شد" in out for out in outputs)


def test_mcp_dynamic_registry_sync():
    """Verify synchronizing discovered MCP tools into Dream's global Tool REGISTRY."""
    reset_mcp_manager()
    mgr = get_mcp_manager()

    client = create_mock_mcp_client(server_id="sync_db", name="Sync DB Server")
    asyncio.run(client.connect())
    mgr.register_client("sync_db", client)

    count = asyncio.run(sync_mcp_tools_to_registry(mgr))
    assert count >= 1
    assert "database_query" in REGISTRY

    # Call through Dream's native Tool abstraction
    dream_tool = REGISTRY["database_query"]
    result = dream_tool.function(query="SELECT 1;")
    assert result["rows"][0]["id"] == 1


def test_mcp_toolset_registration():
    """Verify MCP tools registration into Toolset."""
    ts = get_toolset("mcp")
    assert ts is not None
    assert "mcp_call_tool" in ts.tools
    assert "mcp_list_servers" in ts.tools

    filtered = filter_tools(toolsets=["mcp"])
    assert "mcp_call_tool" in filtered
    assert "mcp_list_servers" in filtered
