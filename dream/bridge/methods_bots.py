"""``bots.*`` RPC surface, registered through the P0 extension seam."""

from __future__ import annotations

from typing import Any

from dream.bots.errors import BotError, BotSecurityError
from dream.bots.service import get_service, reset_service
from dream.bridge.errors import BridgeError, invalid_params
from dream.space.errors import SpaceError, SpaceSecurityError

__all__ = ["HANDLERS", "reset_service"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _wrap(call):  # type: ignore[no-untyped-def]
    try:
        return call()
    except (BotSecurityError, BotError, SpaceSecurityError, SpaceError) as exc:
        raise invalid_params(str(exc)) from None
    except BridgeError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise invalid_params(str(exc)) from None


def _string(data: dict[str, Any], key: str, *, required: bool = True, limit: int = 4_096) -> str:
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise invalid_params(f"{key} must be a non-empty string of at most {limit} characters")
    return value.strip()


def bots_create(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().create(
            _string(data, "space_id", limit=80),
            _string(data, "name", limit=80),
            role_id=_string(data, "role_id", required=False, limit=40) or "secretary",
            model=_string(data, "model", required=False, limit=80) or "echo",
            shape=_string(data, "shape", required=False, limit=20) or None,
            hue=_string(data, "hue", required=False, limit=20) or None,
            yolo=bool(data.get("yolo", False)),
        )
    )


def bots_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().list(_string(data, "space_id", limit=80)))


def bots_get(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().get(_string(data, "bot_id", limit=80)))


def bots_set_instruction(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().set_instruction(
            _string(data, "bot_id", limit=80), _string(data, "text", limit=8_000)
        )
    )


def bots_remember(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().remember(
            _string(data, "bot_id", limit=80), _string(data, "content", limit=2_000)
        )
    )


def bots_recall(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().recall(
            _string(data, "bot_id", limit=80), _string(data, "query", limit=400)
        )
    )


def bots_ask(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().ask(
            _string(data, "bot_id", limit=80), _string(data, "question", limit=4_000)
        )
    )


HANDLERS = {
    "bots.create": bots_create,
    "bots.list": bots_list,
    "bots.get": bots_get,
    "bots.set_instruction": bots_set_instruction,
    "bots.remember": bots_remember,
    "bots.recall": bots_recall,
    "bots.ask": bots_ask,
}
