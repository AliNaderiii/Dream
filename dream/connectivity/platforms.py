"""Static catalog of the six supported connectivity platforms.

The catalog is data, not code: the gateway and the desktop UI both read it to
know each platform's capabilities, its config fields (including which are
secrets and which are required), and the adapter class that serves it.
"""

from __future__ import annotations

from typing import Any

#: One entry per platform. ``fields`` entries are
#: ``{key, label, type, secret?, required?, placeholder?, default?}``.
PLATFORM_CATALOG: dict[str, dict[str, Any]] = {
    "telegram": {
        "name": "telegram",
        "label": "Telegram",
        "description": "Long-polling bot over the Bot API; no inbound port needed.",
        "privacy": "plaintext",
        "max_message_length": 4096,
        "supports_inline": True,
        "supports_attachments": False,
        "fields": [
            {"key": "token", "label": "Bot token", "type": "secret", "required": True,
             "placeholder": "123456:ABC-DEF…"},
            {"key": "api_base_url", "label": "API base URL", "type": "text",
             "placeholder": "https://api.telegram.org"},
        ],
    },
    "discord": {
        "name": "discord",
        "label": "Discord",
        "description": "Gateway WebSocket + REST; slash commands and threads.",
        "privacy": "plaintext",
        "max_message_length": 2000,
        "supports_inline": True,
        "supports_attachments": True,
        "fields": [
            {"key": "bot_token", "label": "Bot token", "type": "secret", "required": True,
             "placeholder": "MT…"},
            {"key": "application_id", "label": "Application ID", "type": "text",
             "placeholder": "123456789012345678"},
            {"key": "register_commands", "label": "Register slash commands on start",
             "type": "boolean", "default": True},
        ],
    },
    "slack": {
        "name": "slack",
        "label": "Slack",
        "description": "Socket Mode (app-level WebSocket); no public endpoint.",
        "privacy": "plaintext",
        "max_message_length": 4000,
        "supports_inline": True,
        "supports_attachments": False,
        "fields": [
            {"key": "app_token", "label": "App-level token (xapp-)", "type": "secret",
             "required": True, "placeholder": "xapp-…"},
            {"key": "bot_token", "label": "Bot token (xoxb-)", "type": "secret",
             "required": True, "placeholder": "xoxb-…"},
        ],
    },
    "whatsapp": {
        "name": "whatsapp",
        "label": "WhatsApp",
        "description": "Cloud API webhook server plus outbound message API.",
        "privacy": "plaintext",
        "max_message_length": 4096,
        "supports_inline": True,
        "supports_attachments": True,
        "fields": [
            {"key": "access_token", "label": "Access token", "type": "secret",
             "required": True, "placeholder": "EAAG…"},
            {"key": "phone_number_id", "label": "Phone number ID", "type": "text",
             "required": True, "placeholder": "123456789012345"},
            {"key": "verify_token", "label": "Webhook verify token", "type": "secret",
             "required": True, "placeholder": "shared-secret"},
            {"key": "app_secret", "label": "App secret (HMAC validation)", "type": "secret",
             "placeholder": "optional"},
            {"key": "port", "label": "Webhook port", "type": "number", "default": 8478},
            {"key": "path", "label": "Webhook path", "type": "text", "default": "/webhook"},
        ],
    },
    "signal": {
        "name": "signal",
        "label": "Signal",
        "description": "signal-cli JSON receive loop; end-to-end encrypted.",
        "privacy": "e2e",
        "max_message_length": 4096,
        "supports_inline": True,
        "supports_attachments": False,
        "fields": [
            {"key": "signal_cli_path", "label": "signal-cli binary", "type": "text",
             "default": "signal-cli", "placeholder": "/usr/local/bin/signal-cli"},
            {"key": "account", "label": "Account number", "type": "text", "required": True,
             "placeholder": "+12025550123"},
        ],
    },
    "email": {
        "name": "email",
        "label": "Email",
        "description": "IMAP IDLE (with polling fallback) and SMTP replies.",
        "privacy": "plaintext",
        "max_message_length": 4000,
        "supports_inline": False,
        "supports_attachments": True,
        "fields": [
            {"key": "imap_host", "label": "IMAP host", "type": "text", "required": True,
             "placeholder": "imap.example.com"},
            {"key": "imap_port", "label": "IMAP port", "type": "number", "default": 993},
            {"key": "imap_user", "label": "IMAP username", "type": "text", "required": True,
             "placeholder": "you@example.com"},
            {"key": "imap_password", "label": "IMAP password", "type": "secret",
             "required": True},
            {"key": "smtp_host", "label": "SMTP host", "type": "text", "required": True,
             "placeholder": "smtp.example.com"},
            {"key": "smtp_port", "label": "SMTP port", "type": "number", "default": 465},
            {"key": "smtp_user", "label": "SMTP username", "type": "text"},
            {"key": "smtp_password", "label": "SMTP password", "type": "secret"},
            {"key": "mailbox", "label": "Mailbox", "type": "text", "default": "INBOX"},
            {"key": "poll_seconds", "label": "Poll interval (seconds)", "type": "number",
             "default": 60},
            {"key": "use_idle", "label": "Use IMAP IDLE", "type": "boolean",
             "default": True},
        ],
    },
}

PLATFORM_NAMES: tuple[str, ...] = tuple(PLATFORM_CATALOG)
