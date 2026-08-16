"""End-to-end tests for P-10 RPC Bridge methods: Provenance, MCP, and ACP."""

import asyncio

import pytest

from dream.bridge.methods import BridgeMethods
from dream.mcp.client import MCPClient
from dream.mcp.models import MCPServerConfig
from dream.mcp.transport import InMemoryTransport
from dream.memory import MemoryStore


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def bridge(tmp_path):
    store = MemoryStore(str(tmp_path / "test_p10.db"))
    return BridgeMethods(
        store=store,
        sessions_path=str(tmp_path / "sessions.json"),
        providers_path=str(tmp_path / "providers.json"),
        provenance_dir=str(tmp_path / "provenance"),
        mcp_config_path=str(tmp_path / "mcp_servers.json"),
        acp_config_path=str(tmp_path / "acp_agents.json"),
    )


def test_provenance_rpc_methods(bridge):
    # 1. Create a session and send a message (generates provenance records)
    sess_res = bridge.session_create({"title": "Provenance Test Session"})
    sid = sess_res["session_id"]

    async def _send():
        stream = await bridge.conversation_send({"session_id": sid, "message": "hello provenance"})
        # drain chunks
        async for _ in stream.chunks:
            pass
        return stream.final

    _run(_send())

    # 2. List provenance records
    list_res = bridge.provenance_list({"session_id": sid})
    assert "records" in list_res
    assert list_res["total"] >= 2
    rec_types = [r["event_type"] for r in list_res["records"]]
    assert "user_message" in rec_types
    assert "model_response" in rec_types

    # 3. Get single record
    rec_id = list_res["records"][0]["record_id"]
    get_res = bridge.provenance_get({"record_id": rec_id})
    assert get_res["record_id"] == rec_id

    # 4. Get provenance tree
    tree_res = bridge.provenance_tree({"session_id": sid})
    assert "nodes" in tree_res
    assert len(tree_res["nodes"]) >= 2

    # 5. Verify integrity chain
    verify_res = bridge.provenance_verify({})
    assert verify_res["valid"] is True
    assert verify_res["records_checked"] >= 2

    # 6. Reproducibility export
    export_res = bridge.provenance_export({"session_id": sid})
    assert "filename" in export_res
    assert export_res["records_count"] >= 2
    assert "base64_data" in export_res


def test_artifact_rpc_methods(bridge, tmp_path):
    # Create dummy artifact file and link it
    artifact_file = tmp_path / "figure.png"
    artifact_file.write_bytes(b"\x89PNGfakeimage")

    rec = bridge.provenance.record(
        event_type="file_write",
        agent_id="test_sess",
        payload={"path": str(artifact_file)},
    )
    bridge.artifacts.link_artifact(str(artifact_file), rec.record_id, tool_name="plot_graph")

    # 1. artifact.get
    art_info = bridge.artifact_get({"path": str(artifact_file)})
    assert art_info["record_id"] == rec.record_id
    assert art_info["tool_name"] == "plot_graph"
    assert "plot_graph" in art_info["lineage_statement"]

    # 2. artifact.list
    art_list = bridge.artifact_list({})
    assert "artifacts" in art_list
    assert len(art_list["artifacts"]) >= 1


def test_mcp_rpc_methods(bridge):
    async def _test():
        # 1. Add MCP Server
        server_info = bridge.mcp_add_server(
            {
                "name": "Math Tools Server",
                "type": "stdio",
                "command": "python",
                "args": ["-m", "math_server"],
            }
        )
        sid = server_info["id"]
        assert sid.startswith("mcp_")

        # 2. List servers
        servers = bridge.mcp_list_servers({})["servers"]
        assert any(s["id"] == sid for s in servers)

        # 3. Get server
        s_detail = bridge.mcp_get_server({"server_id": sid})
        assert s_detail["name"] == "Math Tools Server"

        # 4. Toggle tool
        toggle_res = bridge.mcp_toggle_tool(
            {"server_id": sid, "tool_name": "eval", "enabled": False}
        )
        assert toggle_res["saved"] is True

        # 5. Toggle server
        toggle_srv = bridge.mcp_toggle_server({"server_id": sid, "enabled": False})
        assert toggle_srv["enabled"] is False

        # 6. Register in-memory mock client for execution and resources
        mock_cfg = MCPServerConfig(id=sid, name="Math Tools Server", type="stdio")
        transport = InMemoryTransport(mock_cfg)
        transport.register_tool("add_numbers", "Add two numbers", {}, lambda a, b: a + b)
        transport.register_resource("math://formula", "Formula", "Math formula", "E = mc^2")
        mock_client = MCPClient(mock_cfg, transport=transport)
        await mock_client.connect()
        bridge.mcp.register_client(sid, mock_client)

        # List tools
        tools_res = await bridge.mcp_list_tools({"server_id": sid})
        assert len(tools_res["tools"]) == 1
        assert tools_res["tools"][0]["name"] == "add_numbers"

        # Call tool
        call_res = await bridge.mcp_call_tool(
            {"server_id": sid, "tool_name": "add_numbers", "arguments": {"a": 10, "b": 25}}
        )
        assert call_res["result"] == 35

        # List & read resources
        res_list = await bridge.mcp_list_resources({"server_id": sid})
        assert len(res_list["resources"]) == 1
        assert res_list["resources"][0]["uri"] == "math://formula"

        res_read = await bridge.mcp_read_resource({"server_id": sid, "uri": "math://formula"})
        assert res_read["content"] == "E = mc^2"

        # 7. Remove server
        rem_res = bridge.mcp_remove_server({"server_id": sid})
        assert rem_res["removed"] is True

    _run(_test())


def test_acp_rpc_methods(bridge):
    # 1. ACP Server status & config
    status = bridge.acp_server_status({})
    assert status["status"] == "ready"

    start_res = bridge.acp_server_start({"token": "bridge-acp-token"})
    assert start_res["started"] is True
    assert start_res["token_configured"] is True

    # 2. ACP Client Agents
    agents = bridge.acp_client_list_agents({})["agents"]
    assert len(agents) >= 3

    # Add agent
    new_agent = bridge.acp_client_add_agent(
        {
            "name": "Test External Agent",
            "endpoint": "http://localhost:9999",
            "description": "External reviewer",
        }
    )
    aid = new_agent["id"]
    assert aid.startswith("acp_")

    # Remove agent
    rem_agent = bridge.acp_client_remove_agent({"agent_id": aid})
    assert rem_agent["removed"] is True
