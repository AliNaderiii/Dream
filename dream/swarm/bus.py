"""Inter-agent Message Bus and event routing for Swarm nodes."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from dream.swarm.types import SwarmMessage


class MessageBus:
    """Pub/sub and direct messaging hub for swarm agents."""

    def __init__(self, max_history: int = 1000) -> None:
        self.max_history = max_history
        self._subscribers: dict[str, list[Callable[[SwarmMessage], None]]] = {}
        self._history: list[SwarmMessage] = []

    def subscribe(self, topic: str, handler: Callable[[SwarmMessage], None]) -> None:
        """Subscribe handler to a specific topic or wildcard '*'."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[SwarmMessage], None]) -> bool:
        """Unsubscribe handler from topic."""
        if topic in self._subscribers and handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)
            return True
        return False

    def publish(
        self,
        sender_id: str,
        topic: str,
        payload: Any,
        recipient_id: str = "*",
    ) -> SwarmMessage:
        """Publish a message to the bus and notify matching subscribers."""
        msg = SwarmMessage(
            msg_id=f"msg_{uuid.uuid4().hex[:8]}",
            sender_id=sender_id,
            recipient_id=recipient_id,
            topic=topic,
            payload=payload,
            timestamp=time.time(),
        )

        self._history.append(msg)
        if len(self._history) > self.max_history:
            self._history.pop(0)

        # Notify exact topic subscribers
        handlers = list(self._subscribers.get(topic, []))
        # Notify wildcard topic subscribers
        if topic != "*":
            handlers.extend(self._subscribers.get("*", []))

        for h in handlers:
            try:
                h(msg)
            except Exception:
                pass

        return msg

    def send_direct(
        self,
        sender_id: str,
        recipient_id: str,
        topic: str,
        payload: Any,
    ) -> SwarmMessage:
        """Send direct point-to-point message between two specific swarm agents."""
        return self.publish(
            sender_id=sender_id,
            topic=topic,
            payload=payload,
            recipient_id=recipient_id,
        )

    def get_history(
        self,
        topic: str | None = None,
        sender_id: str | None = None,
        recipient_id: str | None = None,
        limit: int = 50,
    ) -> list[SwarmMessage]:
        """Query and filter message history."""
        results = []
        for msg in reversed(self._history):
            if topic and msg.topic != topic:
                continue
            if sender_id and msg.sender_id != sender_id:
                continue
            if recipient_id and msg.recipient_id not in (recipient_id, "*"):
                continue
            results.append(msg)
            if len(results) >= limit:
                break
        return list(reversed(results))

    def clear(self) -> None:
        """Clear all subscribers and history."""
        self._subscribers.clear()
        self._history.clear()
