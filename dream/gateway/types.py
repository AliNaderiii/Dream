"""Type definitions and data models for the Universal Gateway subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PlatformType(str, Enum):
    """Supported platform types for the Dream Gateway."""

    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WEBHOOK = "webhook"
    MATRIX = "matrix"
    API = "api"
    CONSOLE = "console"


class MessageType(str, Enum):
    """Message content and delivery types."""

    TEXT = "text"
    VOICE = "voice"
    FILE = "file"
    IMAGE = "image"
    INTERACTIVE = "interactive"
    SYSTEM = "system"


@dataclass
class DeliveryTarget:
    """Target destination for outbound messages."""

    platform: PlatformType
    recipient_id: str
    channel_id: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_key(self) -> str:
        """Generate a composite lookup key for this target."""
        return f"{self.platform.value}:{self.recipient_id}:{self.channel_id or ''}"


@dataclass
class IncomingMessage:
    """Incoming user or system message received from an external platform."""

    message_id: str
    platform: PlatformType
    sender_id: str
    sender_name: str
    text: str
    channel_id: str | None = None
    thread_id: str | None = None
    message_type: MessageType = MessageType.TEXT
    raw_payload: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def target(self) -> DeliveryTarget:
        """Generate corresponding delivery target for replies."""
        return DeliveryTarget(
            platform=self.platform,
            recipient_id=self.sender_id,
            channel_id=self.channel_id,
            thread_id=self.thread_id,
        )


@dataclass
class ButtonOption:
    """Interactive button option for confirmations and approvals."""

    button_id: str
    label_en: str
    label_fa: str
    payload: str
    style: str = "default"  # 'default', 'primary', 'danger'


@dataclass
class InteractivePrompt:
    """Interactive dialog or approval prompt requiring user selection."""

    prompt_id: str
    title: str
    description: str
    options: list[ButtonOption]
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 120


@dataclass
class InteractionResponse:
    """User response to an interactive prompt or button click."""

    prompt_id: str
    button_id: str
    sender_id: str
    platform: PlatformType
    payload: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OutgoingMessage:
    """Outbound message payload to be formatted and sent to a platform."""

    target: DeliveryTarget
    text: str
    message_type: MessageType = MessageType.TEXT
    interactive: InteractivePrompt | None = None
    reply_to_message_id: str | None = None
    media_url: str | None = None
    media_bytes: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayStatus:
    """Runtime health and connection status of the Gateway."""

    is_running: bool
    active_platforms: list[PlatformType]
    connected_sessions: int
    pending_deliveries: int
    messages_received: int
    messages_sent: int
    uptime_seconds: float
    platform_details: dict[str, dict[str, Any]] = field(default_factory=dict)
