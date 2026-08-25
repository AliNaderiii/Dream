"""Add-only Dream Bridge handlers for the provider hubs domain."""

from __future__ import annotations

import threading
from typing import Any

from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.providerhubs.service import ProviderHubsError, ProviderHubsService

_service: ProviderHubsService | None = None
_lock = threading.Lock()


def _runtime() -> ProviderHubsService:
    global _service
    with _lock:
        if _service is None:
            _service = ProviderHubsService()
        return _service


def reset_service(service: ProviderHubsService | None = None) -> ProviderHubsService | None:
    """Swap the process-wide service (tests)."""
    global _service
    with _lock:
        _service = service
        return _service


def _params(value: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(value, dict):
        merged.update(value)
    elif value is not None:
        raise BridgeError(INVALID_PARAMS, "params must be an object")
    merged.update(kwargs)
    return merged


def _runtime_id(params: dict[str, Any]) -> str:
    value = params.get("runtime_id")
    if not isinstance(value, str) or not value.strip():
        raise BridgeError(INVALID_PARAMS, "runtime_id must be a non-empty string")
    return value.strip()


def _mapped(call):  # type: ignore[no-untyped-def]
    try:
        return call()
    except ProviderHubsError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc


def providerhubs_catalog(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    params = _params(raw, kwargs)
    query = params.get("query", "")
    if not isinstance(query, str) or len(query) > 200:
        raise BridgeError(INVALID_PARAMS, "query must be a string of at most 200 characters")
    return _mapped(lambda: _runtime().catalog(query))


def providerhubs_runtimes(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(raw, kwargs)
    return _mapped(lambda: _runtime().runtimes())


def providerhubs_health(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    params = _params(raw, kwargs)
    runtime_id = _runtime_id(params)
    return _mapped(lambda: _runtime().health(runtime_id))


def providerhubs_models(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    params = _params(raw, kwargs)
    runtime_id = _runtime_id(params)
    return _mapped(lambda: _runtime().models(runtime_id))


def providerhubs_select_model(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    params = _params(raw, kwargs)
    runtime_id = _runtime_id(params)
    model = params.get("model")
    if not isinstance(model, str):
        raise BridgeError(INVALID_PARAMS, "model must be a string")
    return _mapped(lambda: _runtime().select_model(runtime_id, model))


def providerhubs_test(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    params = _params(raw, kwargs)
    runtime_id = _runtime_id(params)
    return _mapped(lambda: _runtime().test(runtime_id))


def providerhubs_diagnose(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    params = _params(raw, kwargs)
    runtime_id = _runtime_id(params)
    return _mapped(lambda: _runtime().diagnose(runtime_id))


def providerhubs_route(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(raw, kwargs)
    return _mapped(lambda: _runtime().route())


def providerhubs_gateway(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(raw, kwargs)
    return _mapped(lambda: _runtime().gateway_status())


def providerhubs_gateway_update(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    params = _params(raw, kwargs)
    return _mapped(lambda: _runtime().gateway_update(params))


def providerhubs_parsers(raw: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(raw, kwargs)
    return _mapped(lambda: _runtime().parsers())


HANDLERS = {
    "providerhubs.catalog": providerhubs_catalog,
    "providerhubs.runtimes": providerhubs_runtimes,
    "providerhubs.health": providerhubs_health,
    "providerhubs.models": providerhubs_models,
    "providerhubs.select_model": providerhubs_select_model,
    "providerhubs.test": providerhubs_test,
    "providerhubs.diagnose": providerhubs_diagnose,
    "providerhubs.route": providerhubs_route,
    "providerhubs.gateway": providerhubs_gateway,
    "providerhubs.gateway_update": providerhubs_gateway_update,
    "providerhubs.parsers": providerhubs_parsers,
}
