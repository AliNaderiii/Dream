"""Dream Multi-Backend Isolated Terminal Engine and Sandboxing Subsystem."""

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

__all__ = [
    "BaseTerminalBackend",
    "LocalTerminalBackend",
    "DockerSandboxBackend",
    "SSHRemoteBackend",
    "TerminalManager",
    "TerminalBackendType",
    "CommandExecutionRequest",
    "CommandExecutionResult",
    "BackendHealth",
    "get_terminal_manager",
    "reset_terminal_manager",
    "terminal_execute",
    "terminal_list_backends",
    "terminal_switch_backend",
    "handle_terminal_command",
]
