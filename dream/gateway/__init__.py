"""Dream Universal Multi-Platform Gateway Package.

Provides a unified communication hub connecting Telegram, Discord, Slack,
HTTP Webhooks, and external messaging channels directly to the Dream agent.
"""

from dream.gateway.cli import main, run_gateway
from dream.gateway.delivery import GatewayDeliveryRouter
from dream.gateway.hooks import GatewayHookManager
from dream.gateway.hub import GatewayHub
from dream.gateway.pairing import PairingManager
from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.platforms.discord import DiscordAdapter
from dream.gateway.platforms.slack import SlackAdapter
from dream.gateway.platforms.telegram import TelegramAdapter
from dream.gateway.platforms.webhook import WebhookAdapter
from dream.gateway.session import GatewaySessionStore, PlatformSession
from dream.gateway.types import (
    ButtonOption,
    DeliveryTarget,
    GatewayStatus,
    IncomingMessage,
    InteractivePrompt,
    MessageType,
    OutgoingMessage,
    PlatformType,
)

__all__ = [
    "GatewayHub",
    "GatewaySessionStore",
    "PlatformSession",
    "GatewayDeliveryRouter",
    "GatewayHookManager",
    "PairingManager",
    "BasePlatformAdapter",
    "TelegramAdapter",
    "DiscordAdapter",
    "SlackAdapter",
    "WebhookAdapter",
    "IncomingMessage",
    "OutgoingMessage",
    "InteractivePrompt",
    "ButtonOption",
    "DeliveryTarget",
    "PlatformType",
    "MessageType",
    "GatewayStatus",
    "run_gateway",
    "main",
]
