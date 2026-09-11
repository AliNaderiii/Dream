"""Platform adapters package for the Universal Gateway subsystem."""

from __future__ import annotations

from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.platforms.discord import DiscordAdapter
from dream.gateway.platforms.email import EmailAdapter
from dream.gateway.platforms.matrix import MatrixAdapter
from dream.gateway.platforms.signal import SignalAdapter
from dream.gateway.platforms.slack import SlackAdapter
from dream.gateway.platforms.telegram import TelegramAdapter
from dream.gateway.platforms.webhook import WebhookAdapter
from dream.gateway.platforms.whatsapp import WhatsAppAdapter

__all__ = [
    "BasePlatformAdapter",
    "DiscordAdapter",
    "EmailAdapter",
    "MatrixAdapter",
    "SignalAdapter",
    "SlackAdapter",
    "TelegramAdapter",
    "WebhookAdapter",
    "WhatsAppAdapter",
]
