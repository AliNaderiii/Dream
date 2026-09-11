"""Comprehensive tests for Dream Multi-Backend Terminal Execution Engine."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.backends.docker import DockerSandboxBackend
from dream.terminal.backends.local import LocalTerminalBackend
from dream.terminal.backends.ssh import SSHRemoteBackend
from dream.terminal.manager import TerminalManager
from dream.terminal.slash import handle_terminal_command
from dream.terminal.tools import (
    get_terminal_manager,
    reset_terminal_manager,
    terminal_execute,
    terminal_list_backends,
    terminal_switch_backend,
)
from dream.terminal.types import (
    BackendHealth,
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)


class MockTerminalBackend(BaseTerminalBackend):
    """Mock backend for verifying execution routing without invoking host subprocesses."""

    def __init__(self, backend_type: TerminalBackendType = TerminalBackendType.MOCK) -> None:
        super().__init__(backend_type)
        self.executed_requests: list[CommandExecutionRequest] = []

    def is_available(self) -> bool:
        return True

    def health_check(self) -> BackendHealth:
        return BackendHealth(backend=self.backend_type, available=True, details="Mock ready")

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        self.executed_requests.append(request)
        return CommandExecutionResult(
            command=request.command,
            returncode=0,
            stdout=f"mock_out:{request.command}",
            stderr="",
            duration_ms=1.5,
            backend=self.backend_type,
        )


def test_local_terminal_backend_execution():
    """Verify local backend executes safe basic commands."""
    backend = LocalTerminalBackend()
    assert backend.is_available() is True

    health = backend.health_check()
    assert health.available is True

    # Test basic command
    cmd = "echo hello_dream" if sys.platform != "win32" else "echo hello_dream"
    req = CommandExecutionRequest(command=cmd, timeout=5.0)
    res = backend.execute(req)

    assert res.is_success is True
    assert "hello_dream" in res.stdout
    assert res.backend == TerminalBackendType.LOCAL


def test_local_terminal_backend_environment_scrubbing():
    """Verify sensitive environment variables are filtered from child subprocesses."""
    backend = LocalTerminalBackend()
    safe_env = backend._build_safe_env({"CUSTOM_VAR": "safe_val"})
    assert "CUSTOM_VAR" in safe_env
    assert safe_env["CUSTOM_VAR"] == "safe_val"

    # Ensure no API keys or secrets are leaked into child
    for k in safe_env:
        assert "OPENAI_API_KEY" not in k
        assert "SECRET_KEY" not in k


def test_local_terminal_output_truncation():
    """Verify output truncation when exceeding max_output_bytes."""
    backend = LocalTerminalBackend()
    # Mocking large output
    req = CommandExecutionRequest(
        command="python -c \"print('A' * 1000)\"",
        max_output_bytes=100,
        timeout=5.0,
    )
    res = backend.execute(req)
    assert res.is_truncated is True
    assert len(res.stdout) < 300
    assert "Truncated" in res.stdout


def test_docker_sandbox_argument_construction():
    """Verify Docker CLI argument generation and volume mounting."""
    sandbox = DockerSandboxBackend(
        image="python:3.11-alpine",
        network_mode="none",
        memory_limit="256m",
        read_only_rootfs=True,
    )
    assert sandbox.backend_type == TerminalBackendType.DOCKER

    req = CommandExecutionRequest(
        command="python -V",
        cwd="/tmp/my_workspace",
        env={"APP_ENV": "sandbox"},
    )

    with patch("shutil.which", return_value="/usr/bin/docker"), \
         patch("subprocess.run") as mock_run, \
         patch("subprocess.Popen") as mock_popen:
        mock_run.return_value = MagicMock(returncode=0)
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("Python 3.11.4\n", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        res = sandbox.execute(req)
        assert res.is_success is True
        assert "Python 3.11.4" in res.stdout

        # Verify arguments passed to Popen
        args = mock_popen.call_args[0][0]
        assert "--network=none" in args
        assert "--memory=256m" in args
        assert "--read-only" in args
        assert "-v" in args


def test_docker_sandbox_unavailable_fallback():
    """Verify graceful error reporting when Docker daemon is unreachable."""
    sandbox = DockerSandboxBackend()
    with patch("shutil.which", return_value=None):
        assert sandbox.is_available() is False
        req = CommandExecutionRequest(command="ls")
        res = sandbox.execute(req)
        assert res.is_success is False
        assert "داکر در دسترس نیست" in res.stderr or "unavailable" in res.stderr


def test_ssh_remote_argument_construction():
    """Verify SSH remote argument construction and command serialization."""
    ssh_backend = SSHRemoteBackend(
        host="remote.dream.ai",
        port=2222,
        user="admin",
        key_path="/path/to/key.pem",
        remote_cwd="/var/app",
    )
    assert ssh_backend.backend_type == TerminalBackendType.SSH

    cmd_args = ssh_backend._build_ssh_cmd("uptime")
    assert "-p" in cmd_args
    assert "2222" in cmd_args
    assert "admin@remote.dream.ai" in cmd_args
    assert "-i" in cmd_args
    assert "/path/to/key.pem" in cmd_args


def test_terminal_manager_security_blocklist_enforcement():
    """Verify TerminalManager blocks forbidden destructive commands."""
    mgr = TerminalManager(enable_security_scan=True)

    # 1. Root wipe attempt
    res1 = mgr.execute("rm -rf /")
    assert res1.returncode == 126
    assert "مسدود شد" in res1.stderr or "blocked" in res1.stderr

    # 2. Fork bomb attempt
    res2 = mgr.execute(":(){ :|:& };:")
    assert res2.returncode == 126
    assert "مسدود شد" in res2.stderr

    # 3. Registry deletion attempt
    res3 = mgr.execute("reg delete HKLM /f")
    assert res3.returncode == 126


def test_terminal_manager_backend_switching():
    """Verify dynamic switching between multiple registered backends."""
    mgr = TerminalManager()
    mock_backend = MockTerminalBackend()
    docker_backend = DockerSandboxBackend()

    mgr.register_backend(mock_backend)
    mgr.register_backend(docker_backend)

    # Switch to mock backend
    ok = mgr.set_active_backend(TerminalBackendType.MOCK)
    assert ok is True
    assert mgr.active_backend_type == TerminalBackendType.MOCK

    res = mgr.execute("git status")
    assert res.stdout == "mock_out:git status"
    assert len(mock_backend.executed_requests) == 1


def test_terminal_tools_and_slash_command():
    """Verify tool wrappers and slash command dispatching."""
    reset_terminal_manager()
    mgr = get_terminal_manager()
    mock_backend = MockTerminalBackend()
    mgr.register_backend(mock_backend)
    mgr.set_active_backend(TerminalBackendType.MOCK)

    # Tool: list backends
    backends_json = terminal_list_backends()
    data = json.loads(backends_json)
    assert "backends" in data
    assert any(b["type"] == "mock" for b in data["backends"])

    # Tool: execute
    exec_json = terminal_execute("ls -la")
    exec_data = json.loads(exec_json)
    assert exec_data["returncode"] == 0
    assert "mock_out:ls -la" in exec_data["stdout"]

    # Tool: switch backend
    switch_res = terminal_switch_backend("local")
    assert "switched to: local" in switch_res

    # Slash command /terminal
    outputs = []
    handle_terminal_command("", output=outputs.append)
    assert any("Terminal Backends" in line for line in outputs)

    outputs.clear()
    handle_terminal_command("set mock", output=outputs.append)
    assert any("تغییر یافت" in line or "set to" in line for line in outputs)
    assert mgr.active_backend_type == TerminalBackendType.MOCK
