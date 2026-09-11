"""Dream Universal Multi-Platform Gateway Package.

Provides a unified communication hub connecting Telegram, Discord, Slack,
HTTP Webhooks, Matrix, WhatsApp, Email, Signal and external messaging channels.
"""

from dream.gateway.cli import main, run_gateway
from dream.gateway.delivery import GatewayDeliveryRouter
from dream.gateway.hooks import GatewayHookManager
from dream.gateway.hub import GatewayHub
from dream.gateway.pairing import PairingManager
from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.platforms.discord import DiscordAdapter
from dream.gateway.platforms.email import EmailAdapter
from dream.gateway.platforms.matrix import MatrixAdapter
from dream.gateway.platforms.signal import SignalAdapter
from dream.gateway.platforms.slack import SlackAdapter
from dream.gateway.platforms.telegram import TelegramAdapter
from dream.gateway.platforms.webhook import WebhookAdapter
from dream.gateway.platforms.whatsapp import WhatsAppAdapter
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
    "BasePlatformAdapter",
    "ButtonOption",
    "DeliveryTarget",
    "DiscordAdapter",
    "EmailAdapter",
    "GatewayDeliveryRouter",
    "GatewayHookManager",
    "GatewayHub",
    "GatewaySessionStore",
    "GatewayStatus",
    "IncomingMessage",
    "InteractivePrompt",
    "MatrixAdapter",
    "MessageType",
    "OutgoingMessage",
    "PairingManager",
    "PlatformSession",
    "PlatformType",
    "SignalAdapter",
    "SlackAdapter",
    "TelegramAdapter",
    "WebhookAdapter",
    "WhatsAppAdapter",
    "main",
    "run_gateway",
]
