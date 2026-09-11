"""Abstract base interface for terminal execution backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from dream.terminal.types import (
    BackendHealth,
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)


class BaseTerminalBackend(ABC):
    """Abstract base class for all terminal execution environments."""

    def __init__(self, backend_type: TerminalBackendType) -> None:
        self.backend_type = backend_type

    @abstractmethod
    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command in the designated environment and return structured result."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend runtime prerequisites are satisfied on this host."""
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> BackendHealth:
        """Perform diagnostic ping and return availability metrics."""
        raise NotImplementedError

    def cleanup(self) -> None:
        """Release background resources or active subprocess handles."""
        return None
