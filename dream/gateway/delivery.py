"""Outbound message delivery router and broadcast engine for Gateway platforms."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

from dream.gateway.types import DeliveryTarget, MessageType, OutgoingMessage, PlatformType

logger = logging.getLogger(__name__)


class GatewayDeliveryRouter:
    """Dispatches outgoing messages and notifications across registered platform adapters."""

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self._lock = threading.RLock()
        self._adapters: dict[PlatformType, Any] = {}
        self._queue: queue.Queue[OutgoingMessage] = queue.Queue()
        self._running = False
        self._worker_thread: threading.Thread | None = None
        self._sent_count = 0

    def register_adapter(self, platform: PlatformType, adapter: Any) -> None:
        """Register an active platform adapter for message delivery."""
        with self._lock:
            self._adapters[platform] = adapter

    def unregister_adapter(self, platform: PlatformType) -> None:
        """Remove a platform adapter."""
        with self._lock:
            self._adapters.pop(platform, None)

    def start(self) -> None:
        """Start the background delivery queue worker thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._delivery_loop,
                name="GatewayDeliveryWorker",
                daemon=True,
            )
            self._worker_thread.start()

    def stop(self) -> None:
        """Stop background delivery worker."""
        with self._lock:
            self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

    def send(self, message: OutgoingMessage, immediate: bool = False) -> bool:
        """Enqueue or immediately send an outbound message."""
        if immediate:
            return self._dispatch_single(message)
        self._queue.put(message)
        return True

    def send_text(
        self,
        platform: PlatformType,
        recipient_id: str,
        text: str,
        channel_id: str | None = None,
        thread_id: str | None = None,
        immediate: bool = False,
    ) -> bool:
        """Convenience method to deliver plain text."""
        msg = OutgoingMessage(
            target=DeliveryTarget(
                platform=platform,
                recipient_id=recipient_id,
                channel_id=channel_id,
                thread_id=thread_id,
            ),
            text=text,
            message_type=MessageType.TEXT,
        )
        return self.send(msg, immediate=immediate)

    def broadcast(
        self,
        text: str,
        targets: list[DeliveryTarget],
    ) -> int:
        """Deliver a broadcast message to multiple targets."""
        count = 0
        for target in targets:
            msg = OutgoingMessage(target=target, text=text, message_type=MessageType.SYSTEM)
            self.send(msg)
            count += 1
        return count

    @property
    def pending_count(self) -> int:
        """Number of messages currently pending delivery."""
        return self._queue.qsize()

    @property
    def sent_count(self) -> int:
        """Total number of successfully delivered messages."""
        return self._sent_count

    def _delivery_loop(self) -> None:
        """Background delivery processing loop."""
        while self._running:
            try:
                msg = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._dispatch_single(msg)
            finally:
                self._queue.task_done()

    def _dispatch_single(self, msg: OutgoingMessage) -> bool:
        """Deliver a single message using the appropriate adapter."""
        platform = msg.target.platform
        adapter = None
        with self._lock:
            adapter = self._adapters.get(platform)

        if not adapter:
            logger.warning(f"No adapter registered for platform: {platform.value}")
            return False

        for attempt in range(1, self.max_retries + 1):
            try:
                success = adapter.send_message(msg)
                if success:
                    with self._lock:
                        self._sent_count += 1
                    return True
                logger.warning(
                    f"Adapter {platform.value} failed delivery "
                    f"(attempt {attempt}/{self.max_retries})"
                )
            except Exception as exc:
                logger.error(
                    f"Error delivering message on {platform.value} (attempt {attempt}): {exc}"
                )

            if attempt < self.max_retries:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        return False
