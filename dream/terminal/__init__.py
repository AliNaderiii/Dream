"""Dream Multi-Backend Isolated Terminal Engine and Sandboxing Subsystem."""

from __future__ import annotations

from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.backends.daytona import DaytonaTerminalBackend
from dream.terminal.backends.docker import DockerTerminalBackend
from dream.terminal.backends.local import LocalTerminalBackend
from dream.terminal.backends.modal import ModalTerminalBackend
from dream.terminal.backends.singularity import SingularityTerminalBackend
from dream.terminal.backends.ssh import SSHTerminalBackend
from dream.terminal.backends.vercel import VercelTerminalBackend
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

__all__ = [
    "BackendHealth",
    "BaseTerminalBackend",
    "CommandExecutionRequest",
    "CommandExecutionResult",
    "DaytonaTerminalBackend",
    "DockerTerminalBackend",
    "LocalTerminalBackend",
    "ModalTerminalBackend",
    "SSHTerminalBackend",
    "SingularityTerminalBackend",
    "TerminalBackendType",
    "TerminalManager",
    "VercelTerminalBackend",
    "get_terminal_manager",
    "handle_terminal_command",
    "reset_terminal_manager",
    "terminal_execute",
    "terminal_list_backends",
    "terminal_switch_backend",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "terminal" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "terminal",
            [
                "terminal_execute",
                "terminal_list_backends",
                "terminal_switch_backend",
            ],
            display_name="Terminal Execution",
            description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        )
except Exception:
    pass
