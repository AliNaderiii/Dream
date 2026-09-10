"""HTTP error description, body truncation, argument parsing, and secret redaction.

The :class:`OpenAIBackend` (in :mod:`dream.agent.backends.base`) uses
these helpers to build a one-line failure detail and a chat-facing reply
without ever echoing raw provider detail. The functions are deliberately
kept small and side-effect free so the backend can be unit-tested with
plain strings.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError

from dream.agent.constants import ERROR_BODY_LIMIT

# Bearer token pattern redacted from any text that reaches a user or a log.
_BEARER = re.compile(r"[Bb]earer\s+\S+")


def _arguments(value: str | dict[str, Any]) -> dict[str, Any]:
    """Coerce a tool-call arguments value (string or dict) into a dict.

    Tool calls from a JSON-mode model sometimes arrive as a JSON string
    and sometimes already-parsed. Anything that does not parse to a dict
    is treated as empty so a downstream caller never sees ``None`` when
    it expects an arguments mapping.
    """
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _error_body(exc: HTTPError, limit: int = ERROR_BODY_LIMIT) -> str:
    """Return an HTTP error's response body, whitespace-collapsed and truncated."""
    try:
        raw = exc.read()
    except (AttributeError, OSError, ValueError):
        return ""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit]} ... (truncated)"


def _describe_http_error(exc: HTTPError) -> str:
    """Describe an HTTP failure, including the explanation the server sent.

    ``str(HTTPError)`` is only ``HTTP Error 400: Bad Request``, which names the
    status and nothing about the cause. The body carries the reason.
    """
    detail = f"HTTP {exc.code} {exc.reason}".strip()
    body = _error_body(exc)
    return f"{detail}: {body}" if body else detail


def _redact(text: str, *secrets: str) -> str:
    """Strip credentials from text before it reaches a user or a log."""
    for secret in secrets:
        if len(secret) >= 4:
            text = text.replace(secret, "***")
    return _BEARER.sub("Bearer ***", text)


def _failure_text(detail: str, attempts: int) -> str:
    """Describe a failed call, naming abandonment when it was retried.

    A single attempt that failed is just the failure. A call that burned
    several attempts against a rate limit must say so, or the owner cannot
    tell a retried failure from an instantaneous one.
    """
    if attempts > 1:
        return f"{detail} \u2014 abandoned after {attempts} attempts"
    return detail


def _provider_failure_reply(status: int, detail: str) -> str:
    """Return the short chat-facing sentence for a provider failure.

    The reply is Persian, matching the rest of the agent's user-facing
    surface; the English message reaches the operator through the
    ``[provider]`` stderr line the backend prints.
    """
    if status == 429:
        return (
            "\u0633\u0647\u0645\u06cc\u0647 \u062a\u0645\u0627\u0645 "
            "\u0634\u062f\u0647\u061b \u06cc\u06a9 \u062f\u0642\u06cc\u0642\u0647 "
            "\u062f\u06cc\u06af\u0631 \u062f\u0648\u0628\u0627\u0631\u0647 "
            "\u0628\u067e\u0631\u0633."
        )
    if 400 <= status < 500:
        return (
            "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0631\u062f "
            "\u0634\u062f\u061b \u062c\u0632\u0626\u06cc\u0627\u062a "
            "\u0631\u0627 \u062f\u0631 \u062a\u0631\u0645\u06cc\u0646\u0627\u0644 "
            "\u0628\u0628\u06cc\u0646."
        )
    if detail.startswith(("URLError:", "TimeoutError:", "ConnectionError:", "OSError:")):
        return (
            "\u0627\u0644\u0627\u0646 \u0628\u0647 \u0633\u0631\u0648\u06cc\u0633 "
            "\u067e\u0627\u0633\u062e\u200c\u06af\u0648\u06cc\u06cc \u0648\u0635\u0644 "
            "\u0646\u0645\u06cc\u200c\u0634\u0648\u0645\u061b \u0627\u062a\u0635\u0627\u0644 "
            "\u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646."
        )
    return (
        "\u06cc\u06a9 \u062e\u0637\u0627\u06cc "
        "\u063a\u06cc\u0631\u0645\u0646\u062a\u0638\u0631\u0647 "
        "\u0631\u062e \u062f\u0627\u062f\u061b \u062c\u0632\u0626\u06cc\u0627\u062a "
        "\u0631\u0627 \u062f\u0631 \u062a\u0631\u0645\u06cc\u0646\u0627\u0644 "
        "\u0628\u0628\u06cc\u0646."
    )
