"""Dream connectivity: one agent, one memory, every chat platform.

This package implements the multi-platform gateway from Prompt P-07
(Phase 3.1–3.6): six standard-library-only adapters (Telegram, Discord,
Slack, WhatsApp, Signal, Email) that normalise every surface's messages into
:class:`~dream.connectivity.models.IncomingMessage` and route them through the
existing :class:`dream.agent.Dream` loop and shared memory store.

Public surface:

* :class:`~dream.connectivity.gateway.Gateway` — the orchestrator;
* :class:`~dream.connectivity.base.PlatformAdapter` — the adapter contract;
* :mod:`dream.connectivity.adapters` — the six bundled adapters;
* :class:`~dream.connectivity.config.ConnectivityConfig` — per-platform
  config with secret redaction;
* :class:`~dream.connectivity.auth.AuthStore` — single-use link codes and
  the linked-user registry;
* :class:`~dream.connectivity.sessions.SessionRegistry` — one Dream per
  ``(platform, user)``;
* :class:`~dream.connectivity.messagelog.MessageLog` — bounded per-platform
  message history (content-stripped for end-to-end-encrypted platforms);
* :mod:`dream.connectivity.websocket` — minimal RFC 6455 client.

Architecture: see ``docs/architecture/connectivity.md``.
"""

from __future__ import annotations

__version__ = "0.1.0"

from dream.connectivity.auth import AuthStore, LinkCode
from dream.connectivity.base import PlatformAdapter, split_text
from dream.connectivity.config import (
    REDACTED_VALUE,
    ConnectivityConfig,
    redact_config,
)
from dream.connectivity.gateway import Gateway
from dream.connectivity.messagelog import MessageLog
from dream.connectivity.models import (
    Attachment,
    IncomingMessage,
    LinkedUser,
    MessageLogEntry,
    PlatformStatus,
)
from dream.connectivity.platforms import PLATFORM_CATALOG, PLATFORM_NAMES
from dream.connectivity.ratelimit import RateLimiter
from dream.connectivity.sessions import ChannelSession, SessionRegistry

__all__ = [
    "Attachment",
    "AuthStore",
    "ChannelSession",
    "ConnectivityConfig",
    "Gateway",
    "IncomingMessage",
    "LinkCode",
    "LinkedUser",
    "MessageLog",
    "MessageLogEntry",
    "PLATFORM_CATALOG",
    "PLATFORM_NAMES",
    "PlatformAdapter",
    "PlatformStatus",
    "RateLimiter",
    "REDACTED_VALUE",
    "SessionRegistry",
    "redact_config",
    "split_text",
    "__version__",
]
