"""Tests for Multi-Backend Isolated Terminal Engine (Local, Docker, SSH, Cloud Sandboxes)."""

from __future__ import annotations

import json

from dream.terminal import (
    CommandExecutionRequest,
    DaytonaTerminalBackend,
    ModalTerminalBackend,
    SingularityTerminalBackend,
    TerminalBackendType,
    TerminalManager,
    VercelTerminalBackend,
    handle_terminal_command,
    reset_terminal_manager,
    terminal_execute,
    terminal_list_backends,
    terminal_switch_backend,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_terminal_manager_backend_registration():
    mgr = TerminalManager(auto_bootstrap_all=True)
    backends = mgr.list_backends()

    types = [b["type"] for b in backends]
    assert "local" in types
    assert "docker" in types
    assert "ssh" in types
    assert "singularity" in types
    assert "modal" in types
    assert "daytona" in types
    assert "vercel" in types


def test_singularity_backend_lifecycle():
    backend = SingularityTerminalBackend(image_path="test.sif")
    health = backend.health_check()
    assert health.backend == TerminalBackendType.SINGULARITY
    assert "Singularity" in health.details

    req = CommandExecutionRequest(command="echo 'test'")
    res = backend.execute(req)
    assert res.backend == TerminalBackendType.SINGULARITY


def test_modal_cloud_backend_lifecycle():
    backend = ModalTerminalBackend(app_name="dream-test-app")
    health = backend.health_check()
    assert health.backend == TerminalBackendType.MODAL

    req = CommandExecutionRequest(command="python --version")
    res = backend.execute(req)
    assert res.is_success is True
    assert "[modal-cloud:dream-test-app]" in res.stdout


def test_daytona_and_vercel_backends():
    daytona = DaytonaTerminalBackend(workspace_id="ws-dev-01")
    d_health = daytona.health_check()
    assert d_health.backend == TerminalBackendType.DAYTONA
    d_res = daytona.execute(CommandExecutionRequest(command="git status"))
    assert "[daytona:ws-dev-01]" in d_res.stdout

    vercel = VercelTerminalBackend(project_id="proj-42")
    v_health = vercel.health_check()
    assert v_health.backend == TerminalBackendType.VERCEL
    v_res = vercel.execute(CommandExecutionRequest(command="node -v"))
    assert "[vercel-sandbox:iad1]" in v_res.stdout


def test_terminal_manager_switching_and_security():
    mgr = TerminalManager(auto_bootstrap_all=True)

    # Switch to modal
    assert mgr.set_active_backend("modal") is True
    assert mgr.active_backend_type == TerminalBackendType.MODAL

    res = mgr.execute("echo 'hello from modal'")
    assert "[modal-cloud:dream-sandbox]" in res.stdout

    # Switch to invalid
    assert mgr.set_active_backend("nonexistent") is False

    # Security blocklist verification
    sec_res = mgr.execute("rm -rf /")
    assert sec_res.returncode == 126
    assert "blocked by security rule" in sec_res.stderr


def test_terminal_tools_and_slash():
    reset_terminal_manager()

    backends_json = terminal_list_backends()
    data = json.loads(backends_json)
    assert "backends" in data
    assert len(data["backends"]) >= 7

    switch_msg = terminal_switch_backend("modal")
    assert "modal" in switch_msg

    exec_json = terminal_execute("ls -la")
    res_dict = json.loads(exec_json)
    assert res_dict["backend"] == "modal"

    # Slash command tests
    lines = []
    handle_terminal_command("backends", output=lines.append)
    assert any("LOCAL" in line for line in lines)
    assert any("MODAL" in line for line in lines)

    lines.clear()
    handle_terminal_command("set daytona", output=lines.append)
    assert any("daytona" in line for line in lines)

    reset_terminal_manager()


def test_toolset_includes_terminal():
    assert "terminal" in BUILTIN_TOOLSETS
    toolset = get_toolset("terminal")
    assert toolset is not None
    assert len(toolset.tools) >= 3
    assert "terminal_execute" in toolset.tools
    assert "terminal_switch_backend" in toolset.tools
