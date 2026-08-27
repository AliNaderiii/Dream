"""``workroom.*`` RPC surface."""

from __future__ import annotations

from typing import Any

from dream.bridge.errors import BridgeError, invalid_params
from dream.space.errors import SpaceError, SpaceSecurityError
from dream.workroom.errors import WorkroomError, WorkroomSecurityError
from dream.workroom.service import get_service, reset_service

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
    except (WorkroomSecurityError, WorkroomError, SpaceSecurityError, SpaceError) as exc:
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


def workroom_create(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    space_id = _string(data, "space_id", required=False, limit=80) or None
    return _wrap(
        lambda: get_service().create(
            _string(data, "name", limit=80),
            space_id=space_id,
            yolo=bool(data.get("yolo", False)),
        )
    )


def workroom_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    del params, kwargs
    return _wrap(lambda: get_service().list())


def workroom_get(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().get(_string(data, "room_id", limit=80)))


def workroom_add_seat(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().add_seat(
            _string(data, "room_id", limit=80),
            _string(data, "name", limit=80),
            role_id=_string(data, "role_id", required=False, limit=40) or "specialist",
            vip=bool(data.get("vip", False)),
            yolo=bool(data.get("yolo", False)),
        )
    )


def workroom_list_seats(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().list_seats(_string(data, "room_id", limit=80)))


def workroom_draft(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().draft(
            _string(data, "room_id", limit=80),
            _string(data, "body", limit=4_000),
            yolo=bool(data.get("yolo", False)),
        )
    )


def workroom_list_drafts(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().list_drafts(_string(data, "room_id", limit=80)))


def workroom_approve(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().approve(
            _string(data, "draft_id", limit=80),
            approved=bool(data.get("approved", False)),
        )
    )


def workroom_deny(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().deny(_string(data, "draft_id", limit=80)))


HANDLERS = {
    "workroom.create": workroom_create,
    "workroom.list": workroom_list,
    "workroom.get": workroom_get,
    "workroom.add_seat": workroom_add_seat,
    "workroom.list_seats": workroom_list_seats,
    "workroom.draft": workroom_draft,
    "workroom.list_drafts": workroom_list_drafts,
    "workroom.approve": workroom_approve,
    "workroom.deny": workroom_deny,
}
