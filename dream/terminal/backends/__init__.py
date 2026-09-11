"""Terminal execution backend implementations."""

from __future__ import annotations

from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.backends.daytona import DaytonaTerminalBackend
from dream.terminal.backends.docker import DockerTerminalBackend
from dream.terminal.backends.local import LocalTerminalBackend
from dream.terminal.backends.modal import ModalTerminalBackend
from dream.terminal.backends.singularity import SingularityTerminalBackend
from dream.terminal.backends.ssh import SSHTerminalBackend
from dream.terminal.backends.vercel import VercelTerminalBackend

__all__ = [
    "BaseTerminalBackend",
    "DaytonaTerminalBackend",
    "DockerTerminalBackend",
    "LocalTerminalBackend",
    "ModalTerminalBackend",
    "SSHTerminalBackend",
    "SingularityTerminalBackend",
    "VercelTerminalBackend",
]
