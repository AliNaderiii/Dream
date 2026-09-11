"""Agent tool definitions for Terminal Multi-Backend execution."""

from __future__ import annotations

import json

from dream.terminal.manager import TerminalManager
from dream.terminal.types import TerminalBackendType

_GLOBAL_TERMINAL_MANAGER: TerminalManager | None = None


def get_terminal_manager() -> TerminalManager:
    """Retrieve or create singleton TerminalManager."""
    global _GLOBAL_TERMINAL_MANAGER
    if _GLOBAL_TERMINAL_MANAGER is None:
        _GLOBAL_TERMINAL_MANAGER = TerminalManager()
    return _GLOBAL_TERMINAL_MANAGER


def reset_terminal_manager() -> None:
    """Reset the global TerminalManager instance for testing."""
    global _GLOBAL_TERMINAL_MANAGER
    _GLOBAL_TERMINAL_MANAGER = None


def terminal_execute(
    command: str,
    backend: str | None = None,
    cwd: str | None = None,
    timeout: float = 30.0,
) -> str:
    """Execute a shell/terminal command across available local or isolated backends.

    Args:
        command: The shell command to execute.
        backend: Optional backend name ('local', 'docker', 'ssh'). Defaults to active backend.
        cwd: Working directory path for execution.
        timeout: Execution timeout in seconds (default 30s).
    """
    mgr = get_terminal_manager()
    b_type = TerminalBackendType(backend.lower()) if backend else None
    result = mgr.execute(command, backend_type=b_type, cwd=cwd, timeout=timeout)
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def terminal_list_backends() -> str:
    """List all registered terminal backends with availability and health metrics."""
    mgr = get_terminal_manager()
    backends = mgr.list_backends()
    return json.dumps({"backends": backends}, ensure_ascii=False, indent=2)


def terminal_switch_backend(backend: str) -> str:
    """Switch the default active terminal backend (e.g. 'docker', 'local', 'ssh')."""
    mgr = get_terminal_manager()
    ok = mgr.set_active_backend(backend)
    if ok:
        return f"Active terminal backend switched to: {backend}"
    return (
        f"Failed to switch to backend: {backend}. "
        "Check available backends with terminal_list_backends."
    )
