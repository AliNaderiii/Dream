"""Central Terminal Execution Manager and multi-backend orchestrator."""

from __future__ import annotations

import logging
import threading
from typing import Any

from dream.security.blocklist import scan as floor_scan
from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.backends.local import LocalTerminalBackend
from dream.terminal.types import (
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)

logger = logging.getLogger(__name__)


class SecurityBlocklistViolation(Exception):
    """Raised when a command violates Layer-3 security floor policies."""
    pass


class TerminalManager:
    """Manages backend registry, security scanning, and command dispatch."""

    def __init__(
        self,
        default_backend: TerminalBackendType = TerminalBackendType.LOCAL,
        enable_security_scan: bool = True,
    ) -> None:
        self.active_backend_type = default_backend
        self.enable_security_scan = enable_security_scan
        self._lock = threading.RLock()
        self._backends: dict[TerminalBackendType, BaseTerminalBackend] = {}

        # Register default local backend
        self.register_backend(LocalTerminalBackend())

    def register_backend(self, backend: BaseTerminalBackend) -> None:
        """Register a terminal backend in the pool."""
        with self._lock:
            self._backends[backend.backend_type] = backend
            logger.info(f"Registered terminal backend: {backend.backend_type.value}")

    def get_backend(
        self,
        backend_type: TerminalBackendType | None = None,
    ) -> BaseTerminalBackend | None:
        """Retrieve a registered backend by type or active default."""
        with self._lock:
            target = backend_type or self.active_backend_type
            return self._backends.get(target)

    def set_active_backend(self, backend_type: TerminalBackendType | str) -> bool:
        """Switch the default terminal backend."""
        with self._lock:
            if isinstance(backend_type, str):
                try:
                    backend_type = TerminalBackendType(backend_type.lower())
                except ValueError:
                    logger.error(f"Unknown terminal backend type: {backend_type}")
                    return False

            if backend_type not in self._backends:
                logger.warning(f"Backend {backend_type.value} is not registered.")
                return False

            self.active_backend_type = backend_type
            logger.info(f"Active terminal backend switched to: {backend_type.value}")
            return True

    def execute(
        self,
        command: str,
        backend_type: TerminalBackendType | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> CommandExecutionResult:
        """Execute command through security filter and active backend."""
        # 1. Layer-3 Security Blocklist Verification
        if self.enable_security_scan:
            finding = floor_scan(command)
            if finding:
                rule_id = finding.rule.rule_id if hasattr(finding, "rule") else "L3-BLOCK"
                name_en = (
                    finding.rule.name_en if hasattr(finding, "rule") else "destructive command"
                )
                err_msg = (
                    f"⛔ اجرای دستور به دلیل نقض قوانین امنیتی مسدود شد: {rule_id}\n"
                    f"Command blocked by security rule: {name_en}"
                )
                logger.warning(f"Terminal command blocked: {command} -> {rule_id}")
                return CommandExecutionResult(
                    command=command,
                    returncode=126,
                    stdout="",
                    stderr=err_msg,
                    duration_ms=0.0,
                    backend=backend_type or self.active_backend_type,
                    error_message=err_msg,
                )

        # 2. Select backend
        backend = self.get_backend(backend_type)
        if not backend:
            target_name = (backend_type or self.active_backend_type).value
            err_msg = f"Terminal backend '{target_name}' is not registered."
            return CommandExecutionResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=err_msg,
                duration_ms=0.0,
                backend=backend_type or self.active_backend_type,
                error_message=err_msg,
            )

        # 3. Dispatch execution
        req = CommandExecutionRequest(
            command=command,
            cwd=cwd,
            env=env or {},
            timeout=timeout,
            backend_type=backend.backend_type,
        )
        return backend.execute(req)

    def list_backends(self) -> list[dict[str, Any]]:
        """Return status and diagnostics for all registered backends."""
        with self._lock:
            results = []
            for b_type, backend in self._backends.items():
                health = backend.health_check()
                results.append({
                    "type": b_type.value,
                    "is_active": b_type == self.active_backend_type,
                    "available": health.available,
                    "details": health.details,
                    "latency_ms": health.latency_ms,
                    "metadata": health.metadata,
                })
            return results
