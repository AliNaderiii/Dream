"""Tests for Agent Client Protocol (ACP) IDE integration and diff tools."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.acp import (
    ACPAgentConfig,
    ACPAgentManager,
    ACPMessage,
    ACPServer,
    ACPSession,
    acp_apply_diff,
    acp_call_agent,
    acp_get_session_status,
    acp_list_agents,
    acp_read_diagnostics,
    get_acp_tools,
    handle_acp_command,
    reset_global_acp,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_acp_models_serialization():
    sess = ACPSession(id="sess_123", title="Test Session")
    assert sess.id == "sess_123"
    d = sess.to_dict()
    assert d["title"] == "Test Session"

    msg = ACPMessage(role="user", content="hello")
    assert msg.role == "user"
    assert msg.to_dict()["content"] == "hello"

    cfg = ACPAgentConfig(
        id="claude_code",
        name="Claude Code",
        endpoint="http://localhost:8001",
        token="my_token",
    )
    assert cfg.to_dict()["token"] == "[REDACTED]"
    assert cfg.to_full_dict()["token"] == "my_token"


def test_acp_server_dispatch_and_auth():
    import asyncio

    async def _runner():
        server = ACPServer(token="valid_secret")

        # Unauthorized request
        status, _, body = await server.handle_request("/acp/v1/info", "GET", {})
        assert status == 401
        assert body["code"] == 401

        # Authorized info request
        headers = {"Authorization": "Bearer valid_secret"}
        status, _, body = await server.handle_request("/acp/v1/info", "GET", headers)
        assert status == 200
        assert body["name"] == "Dream Assistant"
        assert body["capabilities"]["chat"] is True

        # List tools
        status, _, body = await server.handle_request("/acp/v1/tools", "GET", headers)
        assert status == 200
        assert "tools" in body

        # Create session
        status, _, body = await server.handle_request(
            "/acp/v1/sessions", "POST", headers, {"title": "IDE Workspace"}
        )
        assert status == 201
        assert body["title"] == "IDE Workspace"

    asyncio.run(_runner())


def test_acp_agent_manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = str(Path(tmpdir) / "agents.json")
        mgr = ACPAgentManager(config_path=cfg_path)

        agent = mgr.add_agent(
            name="Custom Agent",
            endpoint="http://localhost:9000",
            label="Custom",
        )
        assert agent.name == "Custom Agent"
        assert len(mgr.list_agents()) >= 1

        assert mgr.remove_agent(agent.id) is True
        assert mgr.remove_agent("non_existing") is False


def test_acp_tools_diff_and_diagnostics():
    reset_global_acp()
    tools = get_acp_tools()
    assert len(tools) == 5

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "app.py"
        test_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

        res = acp_apply_diff(str(test_file), "def hello():\n    return 'dream'\n")
        assert res["success"] is True
        assert test_file.read_text(encoding="utf-8") == "def hello():\n    return 'dream'\n"

    # Blocked sensitive path
    blocked_res = acp_apply_diff("/etc/passwd", "evil")
    assert blocked_res["success"] is False
    assert "Permission denied" in blocked_res["error"]

    # Diagnostics
    diag = acp_read_diagnostics("main.py")
    assert diag["success"] is True
    assert len(diag["diagnostics"]) >= 1

    # Status & list agents
    stat = acp_get_session_status()
    assert stat["success"] is True
    agents_res = acp_list_agents()
    assert agents_res["success"] is True

    # Call agent
    call_res = acp_call_agent("claude_code", "Refactor test suite")
    assert call_res["success"] is True
    assert "Response to" in call_res["reply"]

    reset_global_acp()


def test_acp_slash_commands():
    reset_global_acp()
    lines = []
    handle_acp_command("/acp status", output=lines.append)
    assert any("ACP" in line for line in lines)

    lines.clear()
    handle_acp_command("/acp agents", output=lines.append)
    assert any("ACP" in line for line in lines)

    lines.clear()
    handle_acp_command("/acp sessions", output=lines.append)
    assert len(lines) >= 1

    reset_global_acp()


def test_toolset_includes_acp():
    assert "acp" in BUILTIN_TOOLSETS
    toolset = get_toolset("acp")
    assert toolset is not None
    assert len(toolset.tools) >= 5
    assert "acp_apply_diff" in toolset.tools
    assert "acp_read_diagnostics" in toolset.tools
