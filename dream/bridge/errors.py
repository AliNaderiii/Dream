"""Error taxonomy for the Dream bridge.

Maps the JSON-RPC 2.0 error model onto a small, closed set of Dream-specific
codes (see ``docs/bridge/protocol.md`` §4). The taxonomy is *deny-by-default*:
an unmapped exception is never echoed verbatim in production — only its type
name and a sanitised message reach the frontend.

Three concerns live here:

* :data:`ERRORS` — the code table (name ↔ numeric code ↔ message).
* :class:`BridgeError` — the exception handlers raise to choose a code.
* :func:`serialise_error` — turn any ``Exception`` into the JSON-RPC ``error``
  object, applying the mapping and the dev/prod redaction policy.
"""

from __future__ import annotations

import os
import re
from typing import Any

# JSON-RPC 2.0 reserves -32000..-32099 for implementation-defined server errors.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
PROVIDER_ERROR = -32001
AUTH_ERROR = -32002
RATE_LIMITED = -32003
CONTEXT_OVERFLOW = -32004
APPROVAL_REQUIRED = -32005
TOOL_ERROR = -32006
RESOURCE_EXHAUSTED = -32007

#: The closed set of error codes this protocol may emit.
ERRORS: dict[int, str] = {
    PARSE_ERROR: "Parse error",
    INVALID_REQUEST: "Invalid request",
    METHOD_NOT_FOUND: "Method not found",
    INVALID_PARAMS: "Invalid params",
    INTERNAL_ERROR: "Internal error",
    PROVIDER_ERROR: "Provider error",
    AUTH_ERROR: "Authentication error",
    RATE_LIMITED: "Rate limited",
    CONTEXT_OVERFLOW: "Context overflow",
    APPROVAL_REQUIRED: "Approval required",
    TOOL_ERROR: "Tool error",
    RESOURCE_EXHAUSTED: "Resource exhausted",
}

#: Reverse lookup, name → code, for handlers that prefer symbolic codes.
CODE_NAMES: dict[str, int] = {name.replace(" ", "_").lower(): code for code, name in ERRORS.items()}

#: Maximum traceback size attached to ``data`` in dev mode.
TRACEBACK_LIMIT = 8192

# Secrets we strip from any error message before it crosses the wire.
_BEARER_RE = re.compile(r"[Bb]earer\s+\S+")
_SECRET_MARKERS = ("api_key", "apikey", "authorization", "password", "token", "secret")


def _is_dev_mode() -> bool:
    """True when full tracebacks may be attached to error payloads."""
    return os.environ.get("DREAM_DEV", "").strip().lower() in {"1", "true", "yes", "on"}


class BridgeError(Exception):
    """An error with an explicit taxonomy code.

    Handlers raise this to pick the code directly::

        raise BridgeError(INVALID_PARAMS, "memory_id must be an integer")

    Any other exception is mapped by :func:`_map_exception`.
    """

    code: int = INTERNAL_ERROR

    def __init__(self, code: int, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data

    @property
    def fallback_message(self) -> str:
        return ERRORS.get(self.code, "Internal error")


def invalid_params(message: str, **data: Any) -> BridgeError:
    """Convenience constructor for the most common handler error."""
    payload = dict(data) if data else None
    return BridgeError(INVALID_PARAMS, message, data=payload)


def _redact(text: str) -> str:
    """Strip bearer tokens and obvious credential markers from *text*.

    SEC Stage C (G-17): the value-scan pass runs first, so key-shaped
    strings are replaced even when no ``key=`` marker precedes them.
    """
    from dream.security.secrets import redact_text

    text = redact_text(text)
    text = _BEARER_RE.sub("Bearer ***", text)
    if any(marker in text.lower() for marker in _SECRET_MARKERS):
        # Coarse but safe: collapse any ``key=...`` / ``"key":"..."`` value.
        text = re.sub(
            r"(?i)(api[_-]?key|authorization|password|token|secret)\s*[=:]\s*\S+",
            r"\1=***",
            text,
        )
    return text


def _map_exception(exc: BaseException) -> tuple[int, str]:
    """Choose (code, message) for an arbitrary exception.

    Order matters: the most specific signals are matched first. A message that
    looks like an auth problem is reclassified as ``AUTH_ERROR`` regardless of
    the exception type, because provider libraries are inconsistent about which
    exception they raise for a 401.
    """
    if isinstance(exc, BridgeError):
        return exc.code, str(exc) or exc.fallback_message

    message = _redact(str(exc) or type(exc).__name__)
    lowered = message.lower()

    if "429" in lowered or "rate limit" in lowered or "quota" in lowered:
        return RATE_LIMITED, message
    if "context length" in lowered or "too many tokens" in lowered or "context window" in lowered:
        return CONTEXT_OVERFLOW, message
    if (
        "401" in lowered
        or "unauthor" in lowered
        or "invalid api key" in lowered
        or "authentication" in lowered
    ):
        return AUTH_ERROR, message
    if "timeout" in lowered or isinstance(exc, TimeoutError):
        return PROVIDER_ERROR, message
    if isinstance(exc, (ConnectionError, OSError)) and "address" not in lowered:
        return PROVIDER_ERROR, message
    if isinstance(exc, (KeyError,)):
        return INVALID_PARAMS, f"missing parameter: {exc}"
    if isinstance(exc, (TypeError, ValueError)):
        return INVALID_PARAMS, message
    if isinstance(exc, (FileNotFoundError, PermissionError)):
        return TOOL_ERROR, message

    return INTERNAL_ERROR, f"{type(exc).__name__}: {message}"


def serialise_error(exc: BaseException, request_id: Any | None = None) -> dict[str, Any]:
    """Build a JSON-RPC ``{"jsonrpc","id","error"}`` object for *exc*.

    In production the payload carries only ``code`` and a sanitised ``message``.
    In dev mode (``DREAM_DEV=1``) it additionally carries the exception type and
    a capped traceback in ``data``, so a developer can reproduce the failure.
    """
    code, message = _map_exception(exc)
    error: dict[str, Any] = {"code": code, "message": message}

    # Handler-supplied data (e.g. an approval_id) is structured and always
    # crosses the wire — only the dev-only traceback/type are gated.
    data: dict[str, Any] | None = None
    if isinstance(exc, BridgeError) and exc.data:
        data = dict(exc.data)

    if _is_dev_mode():
        data = data if data is not None else {}
        data["type"] = type(exc).__name__
        # Lazily import so the module stays import-cheap in the common path.
        import traceback

        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        if len(tb) > TRACEBACK_LIMIT:
            tb = tb[:TRACEBACK_LIMIT] + "\n... (truncated)"
        data["traceback"] = tb

    if data is not None:
        error["data"] = data

    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def error_from_code(
    code: int, message: str | None = None, *, request_id: Any | None = None, **data: Any
) -> dict[str, Any]:
    """Build an error response object directly from a code (no exception).

    Used for protocol-level errors (parse, framing, version) that never pass
    through a handler.
    """
    error: dict[str, Any] = {"code": code, "message": message or ERRORS.get(code, "Error")}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
