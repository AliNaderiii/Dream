"""``space.*`` RPC surface, registered through the P0 extension seam."""

from __future__ import annotations

from typing import Any

from dream.bridge.errors import BridgeError, invalid_params
from dream.space.errors import SpaceError, SpaceSecurityError
from dream.space.service import get_service, reset_service
from dream.space.store import reset_store

__all__ = ["HANDLERS", "reset_service", "reset_store"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _wrap(call):  # type: ignore[no-untyped-def]
    try:
        return call()
    except (SpaceSecurityError, SpaceError) as exc:
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


def space_catalog(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(params, kwargs)
    return _wrap(lambda: get_service().catalog())


def space_create(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    language = data.get("language", "en")
    ceiling = data.get("ceiling", "guarded")
    if not isinstance(language, str):
        raise invalid_params("language must be a string")
    if not isinstance(ceiling, str):
        raise invalid_params("ceiling must be a string")
    return _wrap(
        lambda: get_service().create(
            _string(data, "name", limit=120), language=language, ceiling=ceiling
        )
    )


def space_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    _params(params, kwargs)
    return _wrap(lambda: get_service().list())


def space_get(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().get(_string(data, "space_id", limit=80)))


def space_archive(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().archive(_string(data, "space_id", limit=80)))


def space_attach_folder(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().attach_folder(
            _string(data, "space_id", limit=80), _string(data, "folder", limit=4_096)
        )
    )


def space_set_instruction(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    path = data.get("path")
    text = data.get("text")
    if path is not None and not isinstance(path, str):
        raise invalid_params("path must be a string")
    if text is not None and not isinstance(text, str):
        raise invalid_params("text must be a string")
    return _wrap(
        lambda: get_service().set_instruction(
            _string(data, "space_id", limit=80), path=path, text=text
        )
    )


def space_ask(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    timeout = data.get("timeout", 8.0)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise invalid_params("timeout must be a number")
    return _wrap(
        lambda: get_service().ask(
            _string(data, "space_id", limit=80),
            _string(data, "role_id", limit=40),
            _string(data, "question", limit=4_000),
            timeout=float(timeout),
        )
    )


def space_propose_draft(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().propose_draft(
            _string(data, "space_id", limit=80), _string(data, "rule", limit=2_000)
        )
    )


def space_list_drafts(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().list_drafts(_string(data, "space_id", limit=80)))


def space_approve_draft(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().approve_draft(_string(data, "draft_id", limit=80)))


def space_deny_draft(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(lambda: get_service().deny_draft(_string(data, "draft_id", limit=80)))


def space_run_draft(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    return _wrap(
        lambda: get_service().run_draft(
            _string(data, "draft_id", limit=80), approved=bool(data.get("approved", False))
        )
    )


HANDLERS = {
    "space.catalog": space_catalog,
    "space.create": space_create,
    "space.list": space_list,
    "space.get": space_get,
    "space.archive": space_archive,
    "space.attach_folder": space_attach_folder,
    "space.set_instruction": space_set_instruction,
    "space.ask": space_ask,
    "space.propose_draft": space_propose_draft,
    "space.list_drafts": space_list_drafts,
    "space.approve_draft": space_approve_draft,
    "space.deny_draft": space_deny_draft,
    "space.run_draft": space_run_draft,
}
