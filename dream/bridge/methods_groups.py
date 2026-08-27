"""``groups.*`` RPC surface."""

from __future__ import annotations

from typing import Any

from dream.bots.errors import BotError, BotSecurityError
from dream.bridge.errors import BridgeError, invalid_params
from dream.groups.errors import GroupError, GroupSecurityError
from dream.groups.service import get_service, reset_service
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
    except (
        GroupSecurityError,
        GroupError,
        BotSecurityError,
        BotError,
        SpaceSecurityError,
        SpaceError,
    ) as exc:
        raise invalid_params(str(exc)) from None
    except BridgeError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise invalid_params(str(exc)) from None


def _string(data: dict[str, Any], key: str, *, required: bool = True, limit: int = 4_096) -> str:
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise invalid_params(f"{key} must be a non-empty string of at most {limit} characters")
    return value.strip()


def _bot_ids(data: dict[str, Any]) -> list[str]:
    raw = data.get("bot_ids")
    if not isinstance(raw, list):
        raise invalid_params("bot_ids must be a list of 2 to 6 bot ids")
    cleaned: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip() or len(item) > 80:
            raise invalid_params("bot_ids must be a list of 2 to 6 bot ids")
        cleaned.append(item.strip())
    return cleaned


def _max_rounds(data: dict[str, Any]) -> int:
    raw = data.get("max_rounds", 3)
    if raw is None:
        return 3
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise invalid_params("max_rounds must be an integer")
    return raw


def groups_start(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().start(
            _string(data, "space_id", limit=80),
            _bot_ids(data),
            _string(data, "question", limit=4_000),
            yolo=bool(data.get("yolo", False)),
            max_rounds=_max_rounds(data),
        )
    )


def groups_get(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().get(_string(data, "group_id", limit=80)))


def groups_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().list(_string(data, "space_id", limit=80)))


HANDLERS = {
    "groups.start": groups_start,
    "groups.get": groups_get,
    "groups.list": groups_list,
}
