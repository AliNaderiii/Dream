"""Type definitions and data models for the Terminal Execution subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TerminalBackendType(str, Enum):
    """Supported terminal execution backend types."""

    LOCAL = "local"
    DOCKER = "docker"
    SSH = "ssh"
    MOCK = "mock"


@dataclass
class CommandExecutionRequest:
    """Request payload for executing a shell/terminal command."""

    command: str
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    backend_type: TerminalBackendType | None = None
    max_output_bytes: int = 65_536
    interactive: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandExecutionResult:
    """Result of a command executed on a terminal backend."""

    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    backend: TerminalBackendType
    is_truncated: bool = False
    timed_out: bool = False
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        """Check if execution completed with exit code 0."""
        return self.returncode == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "backend": self.backend.value,
            "is_truncated": self.is_truncated,
            "timed_out": self.timed_out,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BackendHealth:
    """Diagnostic health status of a terminal backend."""

    backend: TerminalBackendType
    available: bool
    details: str
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
