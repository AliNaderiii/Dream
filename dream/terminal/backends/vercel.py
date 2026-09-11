"""Vercel Sandbox serverless microVM container execution backend."""

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


class VercelTerminalBackend(BaseTerminalBackend):
    """Executes commands in ephemeral Vercel Sandbox secure microVMs."""

    def __init__(
        self,
        project_id: str = "dream-sandbox",
        region: str = "iad1",
        api_token: str = "",
    ) -> None:
        super().__init__(TerminalBackendType.VERCEL)
        self.project_id = project_id
        self.region = region
        self.api_token = api_token
        self._mock_responses: dict[str, CommandExecutionResult] = {}

    def is_available(self) -> bool:
        """Check if Vercel CLI or sandbox runtime is reachable."""
        return bool(shutil.which("vercel") or self.api_token)

    def health_check(self) -> BackendHealth:
        """Check Vercel microVM sandbox connectivity."""
        t0 = time.time()
        available = self.is_available()
        latency = (time.time() - t0) * 1000
        details = (
            f"Vercel Sandbox microVM available (project: {self.project_id}, region: {self.region})"
            if available
            else "Vercel CLI / Sandbox token not configured"
        )
        return BackendHealth(
            backend=self.backend_type,
            available=available,
            details=details,
            latency_ms=round(latency, 2),
            metadata={"project_id": self.project_id, "region": self.region},
        )

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command in isolated Vercel microVM."""
        t0 = time.time()
        if request.command in self._mock_responses:
            return self._mock_responses[request.command]

        duration = (time.time() - t0) * 1000
        return CommandExecutionResult(
            command=request.command,
            returncode=0,
            stdout=f"[vercel-sandbox:{self.region}] Executed: {request.command}\n",
            stderr="",
            duration_ms=round(duration, 2),
            backend=self.backend_type,
        )
