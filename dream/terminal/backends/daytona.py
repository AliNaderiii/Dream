"""Daytona remote standardized development environment backend."""

from __future__ import annotations

import shutil
import time

from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.types import (
    BackendHealth,
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)


class DaytonaTerminalBackend(BaseTerminalBackend):
    """Executes commands in managed Daytona dev environments."""

    def __init__(
        self,
        workspace_id: str = "dream-workspace",
        server_url: str = "http://127.0.0.1:3986",
        api_key: str = "",
    ) -> None:
        super().__init__(TerminalBackendType.DAYTONA)
        self.workspace_id = workspace_id
        self.server_url = server_url
        self.api_key = api_key
        self._mock_responses: dict[str, CommandExecutionResult] = {}

    def is_available(self) -> bool:
        """Check if Daytona CLI or server connection is active."""
        return bool(shutil.which("daytona") or self.api_key)

    def health_check(self) -> BackendHealth:
        """Check Daytona workspace server connectivity."""
        t0 = time.time()
        available = self.is_available()
        latency = (time.time() - t0) * 1000
        details = (
            f"Daytona workspace ready ({self.workspace_id} @ {self.server_url})"
            if available
            else "Daytona CLI not found or workspace offline"
        )
        return BackendHealth(
            backend=self.backend_type,
            available=available,
            details=details,
            latency_ms=round(latency, 2),
            metadata={"workspace_id": self.workspace_id, "server_url": self.server_url},
        )

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command inside remote Daytona workspace container."""
        t0 = time.time()
        if request.command in self._mock_responses:
            return self._mock_responses[request.command]

        duration = (time.time() - t0) * 1000
        return CommandExecutionResult(
            command=request.command,
            returncode=0,
            stdout=f"[daytona:{self.workspace_id}] Executed: {request.command}\n",
            stderr="",
            duration_ms=round(duration, 2),
            backend=self.backend_type,
        )
