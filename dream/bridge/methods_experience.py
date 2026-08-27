"""``experience.*`` RPC surface."""

from __future__ import annotations

from typing import Any

from dream.bots.errors import BotError, BotSecurityError
from dream.bridge.errors import BridgeError, invalid_params
from dream.experience.errors import ExperienceError, ExperienceSecurityError
from dream.experience.service import get_service, reset_service

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
        ExperienceSecurityError,
        ExperienceError,
        BotSecurityError,
        BotError,
    ) as exc:
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


def experience_capture(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().capture(
            _string(data, "bot_id", limit=80),
            _string(data, "question", limit=4_000),
            yolo=bool(data.get("yolo", False)),
        )
    )


def experience_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    bot_id = _string(data, "bot_id", required=False, limit=80) or None
    return _wrap(lambda: get_service().list(bot_id))


def experience_approve(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().approve(
            _string(data, "draft_id", limit=80),
            approved=bool(data.get("approved", False)),
        )
    )


def experience_deny(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().deny(_string(data, "draft_id", limit=80)))


HANDLERS = {
    "experience.capture": experience_capture,
    "experience.list": experience_list,
    "experience.approve": experience_approve,
    "experience.deny": experience_deny,
}
