"""Add-only Dream Bridge handlers for the Data Q&A domain."""

from __future__ import annotations

import threading
from typing import Any

from dream.bridge.errors import INVALID_PARAMS, RESOURCE_EXHAUSTED, TOOL_ERROR, BridgeError
from dream.bridge.streams import Stream, stream_chunks
from dream.dataqa.service import DataQAError, DataQAService

_service: DataQAService | None = None
_lock = threading.Lock()


def _runtime() -> DataQAService:
    global _service
    with _lock:
        if _service is None:
            _service = DataQAService()
        return _service


def _params(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BridgeError(INVALID_PARAMS, "params must be an object")
    return value


def _required_string(params: dict[str, Any], key: str, *, max_length: int = 2_000) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise BridgeError(
            INVALID_PARAMS, f"{key} must be a non-empty string of at most {max_length} characters"
        )
    return value.strip()


def _optional_source(params: dict[str, Any]) -> str | None:
    source = params.get("source")
    if source is not None and (
        not isinstance(source, str) or len(source) > 4_096 or "\x00" in source
    ):
        raise BridgeError(INVALID_PARAMS, "source must be a safe string of at most 4096 characters")
    return source


def _mapped(call):  # type: ignore[no-untyped-def]
    try:
        return call()
    except DataQAError as exc:
        message = str(exc)
        code = RESOURCE_EXHAUSTED if "quota" in message.lower() else TOOL_ERROR
        raise BridgeError(code, message) from exc
    except (TypeError, ValueError) as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc


def sessions_create(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    params = _params(raw)
    source = _optional_source(params)
    query = params.get("query", "")
    dataset_id = params.get("dataset_id")
    if not isinstance(query, str) or len(query) > 2_000:
        raise BridgeError(INVALID_PARAMS, "query must be a string of at most 2000 characters")
    if dataset_id is not None and (
        not isinstance(dataset_id, str) or not dataset_id or len(dataset_id) > 256
    ):
        raise BridgeError(
            INVALID_PARAMS, "dataset_id must be a non-empty string of at most 256 characters"
        )
    return _mapped(
        lambda: _runtime().create_session(source=source, query=query, dataset_id=dataset_id)
    )


def sessions_list(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    _params(raw)
    return _mapped(lambda: _runtime().list_sessions())


def sessions_get(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    params = _params(raw)
    session_id = _required_string(params, "session_id", max_length=32)
    return _mapped(lambda: _runtime().get_session(session_id))


def sessions_delete(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    params = _params(raw)
    session_id = _required_string(params, "session_id", max_length=32)
    return _mapped(lambda: _runtime().delete_session(session_id))


def dataqa_discover(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    params = _params(raw)
    query, source = params.get("query", ""), _optional_source(params)
    if not isinstance(query, str) or len(query) > 2_000:
        raise BridgeError(INVALID_PARAMS, "query must be a string of at most 2000 characters")
    limit = params.get("limit", 20)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise BridgeError(INVALID_PARAMS, "limit must be an integer from 1 to 100")
    return _mapped(lambda: _runtime().discover(query, source, limit=limit))


async def dataqa_ask(raw: dict[str, Any] | None = None) -> Stream:
    params = _params(raw)
    session_id = _required_string(params, "session_id", max_length=32)
    question = _required_string(params, "question")
    timeout = params.get("timeout", 10.0)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0.2 <= timeout <= 30
    ):
        raise BridgeError(INVALID_PARAMS, "timeout must be between 0.2 and 30 seconds")
    force_chart = params.get("chart")
    if force_chart is not None and not isinstance(force_chart, bool):
        raise BridgeError(INVALID_PARAMS, "chart must be a boolean")

    def produce() -> dict[str, Any]:
        return _mapped(
            lambda: _runtime().ask(
                session_id, question, timeout=float(timeout), force_chart=force_chart
            )
        )

    return await stream_chunks(
        produce, to_text=lambda value: value["final_answer"]["answer"], max_chars=24
    )


def dataqa_chart(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    params = _params(raw)
    session_id = _required_string(params, "session_id", max_length=32)
    return _mapped(lambda: _runtime().chart(session_id))


def dataqa_reset(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    params = _params(raw)
    session_id = _required_string(params, "session_id", max_length=32)
    return _mapped(lambda: _runtime().reset(session_id))


HANDLERS = {
    "dataqa.sessions.create": sessions_create,
    "dataqa.sessions.list": sessions_list,
    "dataqa.sessions.get": sessions_get,
    "dataqa.sessions.delete": sessions_delete,
    "dataqa.discover": dataqa_discover,
    "dataqa.ask": dataqa_ask,
    "dataqa.chart": dataqa_chart,
    "dataqa.reset": dataqa_reset,
}
