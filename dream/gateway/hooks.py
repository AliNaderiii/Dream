"""Lifecycle and interception hooks for the Universal Gateway subsystem."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from dream.gateway.session import PlatformSession
from dream.gateway.types import IncomingMessage, InteractivePrompt, OutgoingMessage

logger = logging.getLogger(__name__)


class GatewayHookManager:
    """Thread-safe event hook manager for gateway lifecycle events."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._hooks: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def register(self, event_name: str, handler: Callable[..., Any]) -> None:
        """Register a callback for a specific lifecycle event."""
        with self._lock:
            self._hooks[event_name].append(handler)

    def unregister(self, event_name: str, handler: Callable[..., Any]) -> bool:
        """Unregister an existing event callback."""
        with self._lock:
            if handler in self._hooks[event_name]:
                self._hooks[event_name].remove(handler)
                return True
            return False

    def trigger(self, event_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Trigger all registered hooks for an event and collect non-failing results."""
        with self._lock:
            handlers = list(self._hooks.get(event_name, []))

        results = []
        for handler in handlers:
            try:
                res = handler(*args, **kwargs)
                results.append(res)
            except Exception as exc:
                logger.error(f"Gateway hook error in '{event_name}': {exc}", exc_info=True)
        return results

    # Typed convenience dispatchers
    def on_message_received(self, message: IncomingMessage) -> None:
        """Trigger message received hooks."""
        self.trigger("message_received", message)

    def on_before_turn(self, message: IncomingMessage, session: PlatformSession) -> None:
        """Trigger before turn execution hooks."""
        self.trigger("before_turn", message, session)

    def on_turn_completed(self, message: IncomingMessage, response_text: str) -> None:
        """Trigger turn completed hooks."""
        self.trigger("turn_completed", message, response_text)

    def on_approval_requested(self, prompt: InteractivePrompt) -> None:
        """Trigger security approval requested hooks."""
        self.trigger("approval_requested", prompt)

    def on_delivery_dispatched(self, message: OutgoingMessage) -> None:
        """Trigger delivery dispatched hooks."""
        self.trigger("delivery_dispatched", message)
