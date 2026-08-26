"""``liveloop.*`` RPC surface, registered through the P0 extension seam."""

from __future__ import annotations

from typing import Any

from dream.bridge.errors import BridgeError, invalid_params
from dream.liveloop.errors import LiveLoopError, LiveLoopSecurityError
from dream.liveloop.service import get_service, reset_service
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
    except (LiveLoopSecurityError, LiveLoopError, SpaceSecurityError, SpaceError) as exc:
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


def liveloop_route_snapshot(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    bar = data.get("bar_provider")
    pane = data.get("pane_provider")
    model = data.get("pane_model")
    if bar is not None and not isinstance(bar, str):
        raise invalid_params("bar_provider must be a string")
    if pane is not None and not isinstance(pane, str):
        raise invalid_params("pane_provider must be a string")
    if model is not None and not isinstance(model, str):
        raise invalid_params("pane_model must be a string")
    return _wrap(
        lambda: get_service().route_snapshot(
            bar_provider=bar, pane_provider=pane, pane_model=model
        )
    )


def liveloop_arm_draft(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().arm_draft(
            _string(data, "draft_id", limit=80), approved=bool(data.get("approved", False))
        )
    )


def liveloop_role_turn(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    timeout = data.get("timeout", 8.0)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise invalid_params("timeout must be a number")
    return _wrap(
        lambda: get_service().role_turn(
            _string(data, "space_id", limit=80),
            _string(data, "role_id", limit=40),
            _string(data, "question", limit=4_000),
            live=bool(data.get("live", False)),
            timeout=float(timeout),
        )
    )


def liveloop_role_catalog(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().role_catalog(_string(data, "space_id", limit=80)))


HANDLERS = {
    "liveloop.route_snapshot": liveloop_route_snapshot,
    "liveloop.arm_draft": liveloop_arm_draft,
    "liveloop.role_turn": liveloop_role_turn,
    "liveloop.role_catalog": liveloop_role_catalog,
}
