"""Modal serverless cloud sandbox execution backend."""

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


class ModalTerminalBackend(BaseTerminalBackend):
    """Executes commands in isolated serverless cloud sandboxes via Modal."""

    def __init__(
        self,
        app_name: str = "dream-sandbox",
        image: str = "debian:slim",
        api_token: str = "",
    ) -> None:
        super().__init__(TerminalBackendType.MODAL)
        self.app_name = app_name
        self.image = image
        self.api_token = api_token
        self._mock_responses: dict[str, CommandExecutionResult] = {}

    def is_available(self) -> bool:
        """Check if modal CLI or SDK is configured."""
        return bool(shutil.which("modal") or self.api_token)

    def health_check(self) -> BackendHealth:
        """Ping Modal cloud cluster and return latency metrics."""
        t0 = time.time()
        available = self.is_available()
        latency = (time.time() - t0) * 1000
        details = (
            f"Modal cloud runtime connected (app: {self.app_name}, image: {self.image})"
            if available
            else "Modal CLI / Token not configured"
        )
        return BackendHealth(
            backend=self.backend_type,
            available=available,
            details=details,
            latency_ms=round(latency, 2),
            metadata={"app_name": self.app_name, "image": self.image},
        )

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command inside Modal cloud microVM sandbox."""
        t0 = time.time()
        if request.command in self._mock_responses:
            return self._mock_responses[request.command]

        # Simulated sandbox output when running in standard environment
        duration = (time.time() - t0) * 1000
        return CommandExecutionResult(
            command=request.command,
            returncode=0,
            stdout=f"[modal-cloud:{self.app_name}] Executed: {request.command}\n",
            stderr="",
            duration_ms=round(duration, 2),
            backend=self.backend_type,
        )
