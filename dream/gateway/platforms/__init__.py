"""Platform adapters for external messaging and communication protocols."""

from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.platforms.discord import DiscordAdapter
from dream.gateway.platforms.slack import SlackAdapter
from dream.gateway.platforms.telegram import TelegramAdapter
from dream.gateway.platforms.webhook import WebhookAdapter

__all__ = [
    "BasePlatformAdapter",
    "TelegramAdapter",
    "DiscordAdapter",
    "SlackAdapter",
    "WebhookAdapter",
]
