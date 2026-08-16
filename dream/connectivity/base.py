"""The adapter contract and text-splitting helper shared by every platform.

The gateway owns :class:`PlatformAdapter` implementations and never the other
way around: adapters receive their incoming-message callback through the
constructor (``on_message``) and have no back-reference to the gateway.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from dream.connectivity.models import IncomingMessage, PlatformStatus

logger = logging.getLogger(__name__)

#: Callback signature every adapter uses to deliver normalised messages.
OnMessage = Callable[[IncomingMessage], Awaitable[None]]


def split_text(text: str, limit: int) -> list[str]:
    """Split *text* into chunks no longer than *limit* characters.

    Chunks prefer word boundaries and never exceed the platform's maximum
    message length, so a long agent reply survives every transport.
    """
    if limit <= 0:
        raise ValueError("limit must be a positive integer")
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # A single word longer than the limit is hard-split mid-word.
        while len(word) > limit:
            chunks.append(word[:limit])
            word = word[limit:]
        current = word
    if current:
        chunks.append(current)
    return chunks


class PlatformAdapter(ABC):
    """Contract every connectivity adapter implements.

    Subclasses declare their capabilities as class attributes, take their
    per-platform config dict and incoming-message callback in the constructor,
    run their I/O inside a worker task started by :meth:`start`, and stop
    cleanly on :meth:`stop`.
    """

    platform_name: ClassVar[str] = ""
    max_message_length: ClassVar[int] = 4_000
    supports_inline: ClassVar[bool] = False
    supports_attachments: ClassVar[bool] = False
    #: Content privacy: "plaintext" (transport may see content) or "e2e"
    #: (end-to-end encrypted — the message log must strip content).
    privacy: ClassVar[str] = "plaintext"

    def __init__(self, config: dict[str, Any], *, on_message: OnMessage) -> None:
        if not self.platform_name:
            raise TypeError("platform_name must be a non-empty ClassVar")
        self._config = dict(config or {})
        self._on_message = on_message
        self._status = PlatformStatus(platform=self.platform_name)

    # -- lifecycle ------------------------------------------------------- #

    @abstractmethod
    async def start(self) -> None:
        """Begin polling/connecting. Must return after the worker is spawned."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop cleanly: cancel workers, close sockets, join threads."""

    # -- outbound -------------------------------------------------------- #

    @abstractmethod
    async def send_message(
        self,
        user_id: str,
        text: str,
        attachments: list | None = None,
    ) -> None:
        """Send *text* to one chat user, splitting is the caller's job."""

    @abstractmethod
    async def send_typing_indicator(self, user_id: str) -> None:
        """Signal that the agent is composing. Best-effort on every platform."""

    # -- observation ----------------------------------------------------- #

    @property
    def is_running(self) -> bool:
        """Whether :meth:`start` has been called and :meth:`stop` has not."""
        return self._status.running

    @property
    def status(self) -> PlatformStatus:
        """A snapshot of this adapter's observable state."""
        return self._status

    @property
    def config(self) -> dict[str, Any]:
        """The adapter's config dict (callers must not leak secret values)."""
        return self._config

    # -- helpers for subclasses ------------------------------------------ #

    async def deliver(self, message: IncomingMessage) -> None:
        """Normalise and hand one platform event to the gateway callback."""
        await self._on_message(message)

    def _note_activity(self) -> None:
        """Stamp the adapter status with a fresh last-activity time."""
        from dream.connectivity.models import utc_now

        self._status.last_activity = utc_now()

    def _mark_error(self, error: str, *, running: bool = False) -> None:
        """Record a failure on the status object without raising."""
        self._status.error = error
        self._status.running = running
        logger.warning("%s adapter error: %s", self.platform_name, error)
