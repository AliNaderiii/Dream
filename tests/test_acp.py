"""Tests for Dream's Agent Client Protocol (ACP) Server, Client, Backend, and Replay."""

import asyncio

from dream.acp.manager import ACPAgentManager
from dream.acp.server import ACPServer


def _run(coro):
    return asyncio.run(coro)


def test_acp_server_endpoints_and_tool_execution(tmp_path):
    async def _test():
        server = ACPServer(token="secret-acp-token")

        # 1. Info / Health
        status, _, body = await server.handle_request(
            "/acp/v1/info", "GET", {"Authorization": "Bearer secret-acp-token"}
        )
        assert status == 200
        assert body["name"] == "Dream Assistant"
        assert body["capabilities"]["chat"] is True

        # 2. Auth check failure
        status, _, _ = await server.handle_request(
            "/acp/v1/info", "GET", {"Authorization": "Bearer wrong-token"}
        )
        assert status == 401

        # 3. List tools
        status, _, body = await server.handle_request(
            "/acp/v1/tools", "GET", {"Authorization": "Bearer secret-acp-token"}
        )
        assert status == 200
        assert "tools" in body
        tool_names = [t["name"] for t in body["tools"]]
        assert "get_datetime" in tool_names

        # 4. Execute tool
        status, _, body = await server.handle_request(
            "/acp/v1/tools/get_datetime",
            "POST",
            {"Authorization": "Bearer secret-acp-token"},
            {"timezone_name": "Asia/Tehran"},
        )
        assert status == 200

        # 5. Session creation & listing
        status, _, body = await server.handle_request(
            "/acp/v1/sessions",
            "POST",
            {"Authorization": "Bearer secret-acp-token"},
            {"title": "Code Review Session"},
        )
        assert status == 201
        sid = body["id"]

        status, _, body = await server.handle_request(
            "/acp/v1/sessions", "GET", {"Authorization": "Bearer secret-acp-token"}
        )
        assert status == 200
        assert any(s["id"] == sid for s in body["sessions"])

        # 6. Chat turn
        status, _, body = await server.handle_request(
            "/acp/v1/messages",
            "POST",
            {"Authorization": "Bearer secret-acp-token"},
            {"session_id": sid, "message": "Hello from external editor!"},
        )
        assert status == 200
        assert "reply" in body
        assert len(body["reply"]) > 0

        # 7. Replay history
        status, _, body = await server.handle_request(
            "/acp/v1/replay",
            "POST",
            {"Authorization": "Bearer secret-acp-token"},
            {
                "session_id": sid,
                "messages": [
                    {"role": "user", "content": "Here is step 1 of my analysis."},
                    {"role": "assistant", "content": "Understood."},
                ],
                "instruction": "Summarize the analysis so far.",
            },
        )
        assert status == 200
        assert "reply" in body

    _run(_test())


def test_acp_agent_manager(tmp_path):
    async def _test():
        config_path = str(tmp_path / "acp_agents.json")
        mgr = ACPAgentManager(config_path=config_path)

        # Preloaded defaults exist
        agents = mgr.list_agents()
        assert len(agents) >= 3
        agent_names = [a["name"] for a in agents]
        assert "Claude Code (ACP)" in agent_names
        assert "Codex (ACP)" in agent_names

        # Add custom agent
        custom = mgr.add_agent(
            name="Custom Analyzer",
            endpoint="http://localhost:9000",
            description="Specialized math agent",
        )
        assert custom.id.startswith("acp_")
        assert len(mgr.list_agents()) == len(agents) + 1

        # Remove agent
        mgr.remove_agent(custom.id)
        assert len(mgr.list_agents()) == len(agents)

    _run(_test())
