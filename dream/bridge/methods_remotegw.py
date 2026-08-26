"""``remotegw.*`` RPC surface, registered through the P0 extension seam."""

from __future__ import annotations

from typing import Any

from dream.bridge.errors import BridgeError, invalid_params
from dream.remotegw.errors import RemoteGwError, RemoteGwSecurityError
from dream.remotegw.service import get_service, reset_service

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
    except (RemoteGwSecurityError, RemoteGwError) as exc:
        raise invalid_params(str(exc)) from None
    except BridgeError:
        raise
    except (TypeError, ValueError) as exc:
        raise invalid_params(str(exc)) from None


def _string(data: dict[str, Any], key: str, *, required: bool = True, limit: int = 4_096) -> str:
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise invalid_params(f"{key} must be a non-empty string of at most {limit} characters")
    return value.strip()


def remotegw_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(params, kwargs)
    return _wrap(lambda: get_service().status())


def remotegw_preview(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    host = data.get("host")
    port = data.get("port")
    if host is not None and not isinstance(host, str):
        raise invalid_params("host must be a string")
    if port is not None and not isinstance(port, int):
        raise invalid_params("port must be an integer")
    return _wrap(
        lambda: get_service().preview(lan=bool(data.get("lan", False)), host=host, port=port)
    )


def remotegw_start(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    host = data.get("host")
    port = data.get("port")
    if host is not None and not isinstance(host, str):
        raise invalid_params("host must be a string")
    if port is not None and not isinstance(port, int):
        raise invalid_params("port must be an integer")
    return _wrap(
        lambda: get_service().start(lan=bool(data.get("lan", False)), host=host, port=port)
    )


def remotegw_stop(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(params, kwargs)
    return _wrap(lambda: get_service().stop())


def remotegw_issue_token(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    scope = data.get("scope", "read")
    label = data.get("label", "Remote")
    if not isinstance(scope, str) or not isinstance(label, str):
        raise invalid_params("scope and label must be strings")
    return _wrap(lambda: get_service().issue_token(scope=scope, label=label))


def remotegw_revoke_token(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().revoke_token(_string(data, "token", limit=200)))


def remotegw_list_tokens(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(params, kwargs)
    return _wrap(lambda: get_service().tokens.list())


HANDLERS = {
    "remotegw.status": remotegw_status,
    "remotegw.preview": remotegw_preview,
    "remotegw.start": remotegw_start,
    "remotegw.stop": remotegw_stop,
    "remotegw.issue_token": remotegw_issue_token,
    "remotegw.revoke_token": remotegw_revoke_token,
    "remotegw.list_tokens": remotegw_list_tokens,
}
