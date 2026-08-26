"""``gws.*`` RPC surface, registered through the P0 extension seam."""

from __future__ import annotations

from typing import Any

from dream.bridge.errors import BridgeError, invalid_params
from dream.gws.errors import GwsError, GwsSecurityError
from dream.gws.service import get_service, reset_service

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
    except (GwsSecurityError, GwsError) as exc:
        raise invalid_params(str(exc)) from None
    except BridgeError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise invalid_params(str(exc)) from None


def _int(data: dict[str, Any], key: str, default: int = 5) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise invalid_params(f"{key} must be an integer")
    return value


def gws_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    del params, kwargs
    return _wrap(lambda: get_service().status())


def gws_oauth_begin(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    del params, kwargs
    return _wrap(lambda: get_service().oauth_begin())


def gws_oauth_complete(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    state = data.get("state")
    code = data.get("code")
    if not isinstance(state, str) or not state.strip():
        raise invalid_params("state must be a non-empty string")
    if not isinstance(code, str) or not code.strip():
        raise invalid_params("code must be a non-empty string")
    return _wrap(lambda: get_service().oauth_complete(state.strip(), code.strip()))


def gws_disconnect(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    del params, kwargs
    return _wrap(lambda: get_service().disconnect())


def gws_gmail_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: {"text": get_service().gmail_list(_int(data, "max_results"))})


def gws_calendar_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: {"text": get_service().calendar_list(_int(data, "max_results"))})


def gws_drive_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: {"text": get_service().drive_list(_int(data, "max_results"))})


HANDLERS = {
    "gws.status": gws_status,
    "gws.oauth_begin": gws_oauth_begin,
    "gws.oauth_complete": gws_oauth_complete,
    "gws.disconnect": gws_disconnect,
    "gws.gmail_list": gws_gmail_list,
    "gws.calendar_list": gws_calendar_list,
    "gws.drive_list": gws_drive_list,
}
