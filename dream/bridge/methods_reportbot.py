"""``reportbot.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.

=================================  ==================================================
``reportbot.start``               Start the Telegram report bot (long polling)
``reportbot.stop``                Stop the running report bot
``reportbot.status``              Running state, counters, and the event log
=================================  ==================================================
"""

from __future__ import annotations

import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.reporting.telegram_bot import (
    ReportBotError,
    get_report_bot_service,
)

logger = logging.getLogger(__name__)

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _optional_base_url(data: dict[str, Any]) -> str | None:
    value = data.get("api_base_url")
    if value is None:
        return None
    if not isinstance(value, str):
        raise invalid_params("api_base_url must be a string when provided")
    value = value.strip()
    if len(value) > 2048:
        raise invalid_params("api_base_url must be at most 2048 characters")
    return value or None


async def reportbot_start(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Start the report bot. Params: ``token`` (BotFather token), ``api_base_url``."""
    data = _params(params, kwargs)
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        raise invalid_params("token must be a non-empty BotFather token string")
    if len(token) > 256:
        raise invalid_params("token must be at most 256 characters")
    api_base_url = _optional_base_url(data)
    service = get_report_bot_service()
    try:
        status = service.start(token, api_base_url)
    except ReportBotError as exc:
        raise invalid_params(str(exc)) from exc
    # Only the fingerprint is logged; the token itself never reaches the log.
    logger.info("reportbot.start → running=%s", status.get("running"))
    return {"success": True, **status}


async def reportbot_stop(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Stop the running report bot (idempotent)."""
    _params(params, kwargs)  # validated and discarded: stop takes no payload
    status = get_report_bot_service().stop()
    return {"success": True, **status}


async def reportbot_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Report running state, counters, and the bounded event log."""
    _params(params, kwargs)  # validated and discarded: status takes no payload
    return get_report_bot_service().status()


HANDLERS = {
    "reportbot.start": reportbot_start,
    "reportbot.stop": reportbot_stop,
    "reportbot.status": reportbot_status,
}
