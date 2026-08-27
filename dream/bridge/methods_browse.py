"""``browse.*`` RPC surface."""

from __future__ import annotations

from typing import Any

from dream.bridge.errors import BridgeError, invalid_params
from dream.browse.errors import BrowseError, BrowseSecurityError
from dream.browse.service import get_service, reset_service

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
    except (BrowseSecurityError, BrowseError) as exc:
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


def browse_propose(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().propose(
            _string(data, "url", limit=2_048),
            yolo=bool(data.get("yolo", False)),
        )
    )


def browse_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    del params, kwargs
    return _wrap(lambda: get_service().list())


def browse_get(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().get(_string(data, "draft_id", limit=80)))


def browse_approve(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().approve(
            _string(data, "draft_id", limit=80),
            approved=bool(data.get("approved", False)),
        )
    )


def browse_deny(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().deny(_string(data, "draft_id", limit=80)))


def browse_follow(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().follow(
            _string(data, "draft_id", limit=80),
            _string(data, "url", limit=2_048),
            yolo=bool(data.get("yolo", False)),
        )
    )


HANDLERS = {
    "browse.propose": browse_propose,
    "browse.list": browse_list,
    "browse.get": browse_get,
    "browse.approve": browse_approve,
    "browse.deny": browse_deny,
    "browse.follow": browse_follow,
}
