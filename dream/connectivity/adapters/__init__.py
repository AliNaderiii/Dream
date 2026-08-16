"""Bundled platform adapters (Telegram, Discord, Slack, WhatsApp, Signal, Email).

:func:`build_adapters` constructs one adapter per platform from the shared
:class:`~dream.connectivity.config.ConnectivityConfig`. Construction never
touches the network and never validates credentials: adapters validate their
config at ``start()`` so a machine without one platform's prerequisites can
still build the rest.
"""

from __future__ import annotations

from dream.connectivity.adapters.discord import DiscordAdapter
from dream.connectivity.adapters.email import EmailAdapter
from dream.connectivity.adapters.signal import SignalAdapter
from dream.connectivity.adapters.slack import SlackAdapter
from dream.connectivity.adapters.telegram import TelegramAdapter
from dream.connectivity.adapters.whatsapp import WhatsAppAdapter
from dream.connectivity.base import OnMessage, PlatformAdapter
from dream.connectivity.config import ConnectivityConfig

__all__ = [
    "DiscordAdapter",
    "EmailAdapter",
    "SignalAdapter",
    "SlackAdapter",
    "TelegramAdapter",
    "WhatsAppAdapter",
    "build_adapters",
]


def build_adapters(config: ConnectivityConfig, *, on_message: OnMessage) -> list[PlatformAdapter]:
    """Build the six bundled adapters, wired to one incoming-message callback."""
    telegram = TelegramAdapter(config.get("telegram"), on_message=on_message)
    discord = DiscordAdapter(config.get("discord"), on_message=on_message)
    slack = SlackAdapter(config.get("slack"), on_message=on_message)
    whatsapp = WhatsAppAdapter(config.get("whatsapp"), on_message=on_message)
    signal = SignalAdapter(config.get("signal"), on_message=on_message)
    email = EmailAdapter(config.get("email"), on_message=on_message)
    return [telegram, discord, slack, whatsapp, signal, email]
