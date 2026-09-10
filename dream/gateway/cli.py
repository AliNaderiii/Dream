"""Command-Line Interface and launcher for the Dream Universal Gateway."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import Any

from dream.gateway.hub import GatewayHub
from dream.gateway.platforms.discord import DiscordAdapter
from dream.gateway.platforms.slack import SlackAdapter
from dream.gateway.platforms.telegram import TelegramAdapter
from dream.gateway.platforms.webhook import WebhookAdapter
from dream.memory import MemoryStore

logger = logging.getLogger("dream.gateway")


def build_gateway_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for the Gateway."""
    parser = argparse.ArgumentParser(
        prog="dream-gateway",
        description="Dream Universal Multi-Platform Gateway (Telegram, Discord, Slack, Webhook).",
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        default=["webhook"],
        choices=["telegram", "discord", "slack", "webhook"],
        help="List of platform adapters to initialize and run (default: webhook)",
    )
    parser.add_argument(
        "--db-path",
        default=os.getenv("DREAM_GATEWAY_DB", "gateway_sessions.db"),
        help="Path to SQLite database for persisting gateway sessions",
    )
    parser.add_argument(
        "--auto-pair",
        action="store_true",
        help="Automatically trust and pair incoming platform users without pairing codes",
    )
    parser.add_argument(
        "--webhook-port",
        type=int,
        default=int(os.getenv("DREAM_WEBHOOK_PORT", "8765")),
        help="Listening port for inbound HTTP Webhook adapter",
    )
    parser.add_argument(
        "--webhook-host",
        default=os.getenv("DREAM_WEBHOOK_HOST", "127.0.0.1"),
        help="Listening host for inbound HTTP Webhook adapter",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logging",
    )
    return parser


def run_gateway(args: argparse.Namespace | None = None, argv: list[str] | None = None) -> int:
    """Launch the Gateway Hub with the configured platform adapters."""
    if args is None:
        parser = build_gateway_parser()
        args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    store = MemoryStore(":memory:")
    hub = GatewayHub(memory_store=store, db_path=args.db_path, auto_pair=args.auto_pair)

    # 1. Telegram
    if "telegram" in args.platforms:
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if tg_token:
            hub.register_adapter(TelegramAdapter(bot_token=tg_token))
        else:
            logger.warning("TELEGRAM_BOT_TOKEN not found in environment; skipping Telegram.")

    # 2. Discord
    if "discord" in args.platforms:
        dc_token = os.getenv("DISCORD_BOT_TOKEN")
        dc_webhook = os.getenv("DISCORD_WEBHOOK_URL")
        if dc_token or dc_webhook:
            hub.register_adapter(DiscordAdapter(bot_token=dc_token, webhook_url=dc_webhook))
        else:
            logger.warning(
                "Neither DISCORD_BOT_TOKEN nor DISCORD_WEBHOOK_URL found; skipping Discord."
            )

    # 3. Slack
    if "slack" in args.platforms:
        slack_token = os.getenv("SLACK_BOT_TOKEN")
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        if slack_token or slack_webhook:
            hub.register_adapter(SlackAdapter(bot_token=slack_token, webhook_url=slack_webhook))
        else:
            logger.warning("Neither SLACK_BOT_TOKEN nor SLACK_WEBHOOK_URL found; skipping Slack.")

    # 4. Webhook
    if "webhook" in args.platforms:
        secret = os.getenv("DREAM_WEBHOOK_SECRET")
        hub.register_adapter(
            WebhookAdapter(
                listen_host=args.webhook_host,
                listen_port=args.webhook_port,
                secret_key=secret,
            )
        )

    # Handle interrupt signal for clean shutdown
    stop_event = threading.Event()

    def _signal_handler(sig: int, frame: Any) -> None:
        logger.info("Termination signal received. Shutting down Gateway Hub...")
        hub.stop()
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    hub.start()
    logger.info(f"Dream Universal Gateway active with platforms: {', '.join(args.platforms)}")

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        hub.stop()

    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for dream-gateway command."""
    return run_gateway(argv=argv)


if __name__ == "__main__":
    sys.exit(main())
