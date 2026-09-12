"""Chaos Testing Simulator: Fault injection and failure resilience verification."""

from __future__ import annotations

from typing import Any

from dream.healing.types import FaultType


class ChaosSimulator:
    """Injects synthetic runtime faults to validate agent fault-tolerance."""

    def __init__(self) -> None:
        self._injected_log: list[dict[str, Any]] = []

    def simulate_fault(
        self,
        fault_type: FaultType,
        target_name: str,
    ) -> Exception:
        """Create standard synthetic exception corresponding to fault type."""
        record = {"fault_type": fault_type.value, "target": target_name}
        self._injected_log.append(record)

        if fault_type == FaultType.RATE_LIMIT:
            return ConnectionError(
                f"RateLimitExceeded: HTTP 429 Too Many Requests on '{target_name}'"
            )
        elif fault_type == FaultType.TIMEOUT:
            return TimeoutError(
                f"ExecutionTimeout: Operation on '{target_name}' exceeded 15.0s deadline"
            )
        elif fault_type == FaultType.SCHEMA_MISMATCH:
            return ValueError(
                f"SchemaValidationError: Unexpected payload shape for '{target_name}'"
            )
        elif fault_type == FaultType.CORRUPTED_STATE:
            return KeyError(
                f"CorruptedSessionState: Key not found in working memory for '{target_name}'"
            )
        elif fault_type == FaultType.NETWORK_DISCONNECT:
            return OSError(
                f"NetworkUnreachable: Socket reset by peer on '{target_name}'"
            )
        else:
            return RuntimeError(
                f"UnhandledToolException: Runtime failure in '{target_name}'"
            )

    def get_injected_history(self) -> list[dict[str, Any]]:
        """Return history of injected chaos events."""
        return list(self._injected_log)

    def reset(self) -> None:
        """Clear chaos injection logs."""
        self._injected_log.clear()
