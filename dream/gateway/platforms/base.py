"""Abstract base platform adapter for the Universal Gateway."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from dream.gateway.types import (
    IncomingMessage,
    InteractivePrompt,
    OutgoingMessage,
    PlatformType,
)


class BasePlatformAdapter(ABC):
    """Abstract interface for all external messaging platform adapters."""

    def __init__(
        self,
        platform: PlatformType,
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        self.platform = platform
        self.message_handler = message_handler
        self.interaction_handler = interaction_handler
        self.is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection or start polling/webhook listener."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully terminate connection and cleanup background listeners."""
        raise NotImplementedError

    @abstractmethod
    def send_message(self, message: OutgoingMessage) -> bool:
        """Send a standard or multimedia message to the platform."""
        raise NotImplementedError

    @abstractmethod
    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send an interactive prompt (buttons, menus, confirmation dialogs)."""
        raise NotImplementedError

    def health_check(self) -> dict[str, Any]:
        """Return diagnostic health and status metrics for this platform adapter."""
        return {
            "platform": self.platform.value,
            "connected": self.is_connected,
            "adapter_class": self.__class__.__name__,
        }
