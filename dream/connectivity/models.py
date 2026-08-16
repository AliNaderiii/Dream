"""Shared data models for the multi-platform connectivity layer.

Every adapter normalises its platform's messages into :class:`IncomingMessage`
and the gateway routes them into one :class:`dream.agent.Dream` per
``(platform, user)`` channel. These value types are the wire shapes the bridge
reports to the desktop UI (see ``docs/bridge/protocol.md`` §3.11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Current time as an aware UTC :class:`datetime`."""

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class Attachment:
    """One attachment carried by an incoming message.

    Adapters that download media (WhatsApp, Signal, Email) populate ``data``
    in memory; adapters that only know a remote URL leave ``data`` as ``None``.
    """

    mime_type: str = "application/octet-stream"
    filename: str | None = None
    data: bytes | None = None
    url: str | None = None
    size: int = 0

    def to_dict(self) -> dict[str, Any]:
        """A JSON-friendly summary that never carries raw attachment bytes."""
        return {
            "mime_type": self.mime_type,
            "filename": self.filename,
            "size": self.size if self.size else (len(self.data) if self.data else 0),
            "url": self.url,
        }


@dataclass(slots=True)
class IncomingMessage:
    """A message from any platform, normalised for the gateway router.

    ``raw`` is the platform-specific escape hatch: adapters stash their
    original payload there (e.g. the Telegram update object) so callbacks can
    react to platform details without the gateway learning them.
    """

    platform: str
    platform_user_id: str
    platform_channel_id: str | None
    text: str
    attachments: list[Attachment] = field(default_factory=list)
    timestamp: datetime = field(default_factory=utc_now)
    message_id: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class PlatformStatus:
    """Observable state of one adapter, reported by ``gateway.status``."""

    platform: str
    running: bool = False
    connected: bool = False
    last_activity: datetime | None = None
    error: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """The JSON shape of §3.11 ``gateway.status`` adapters list."""
        return {
            "platform": self.platform,
            "running": self.running,
            "connected": self.connected,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "error": self.error,
            "detail": self.detail,
        }


@dataclass(slots=True)
class LinkedUser:
    """A chat identity authorised to talk to the agent on one platform."""

    platform: str
    user_id: str
    display_name: str = ""
    linked_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "linked_at": self.linked_at,
        }


@dataclass(slots=True)
class MessageLogEntry:
    """One inbound or outbound message in the per-platform message log.

    For end-to-end-encrypted platforms (``privacy == "e2e"``) the gateway
    stores an empty ``text``: content is never persisted (gate G11).
    """

    platform: str
    direction: str  # "in" | "out"
    user_id: str
    text: str
    timestamp: datetime = field(default_factory=utc_now)
    message_id: str | None = None
    attachments: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "direction": self.direction,
            "user_id": self.user_id,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id,
            "attachments": self.attachments,
        }
