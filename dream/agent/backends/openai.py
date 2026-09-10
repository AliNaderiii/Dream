"""OpenAI-compatible HTTP chat client.

A single class serves the hosted (``api.openai.com``), Aval, and BYOK
routes: the only difference between them is the base URL and the API
key, both of which come from the environment. The class also serves
the local Ollama path through the same OpenAI-compatible protocol
(``/v1`` is appended to the Ollama host by :class:`OllamaBackend`).

The client is intentionally synchronous with a bounded retry loop on
HTTP 429. A provider that hangs is bounded by the per-request
``urlopen`` timeout (60 seconds) and reported as a failure rather
than retried into the wall clock; a provider that returns a rate
limit is alive and may recover, so the retry sleeps an exponentially
growing backoff.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

# The backend reads ``urlopen`` and ``interruptible_sleep`` from the
# ``dream.agent`` facade at call time. Centralising the lookup means
# test fixtures that monkeypatch ``dream.agent.urlopen`` (or the sleep
# helper) reach the same callable the backend uses: a captured local
# reference would diverge the moment the test rewrites the facade.
# Late import keeps the package's partial-init order safe (backends are
# imported from the facade before this module finishes initialising).
import dream.agent
from dream import __version__
from dream.agent.env_config import (
    _resolve_max_retries,
    _resolve_retry_backoff,
    _resolve_temperature,
)
from dream.agent.http_utils import (
    _arguments,
    _describe_http_error,
    _failure_text,
    _provider_failure_reply,
    _redact,
)
from dream.agent.user_agent import _resolve_user_agent


def _urlopen(request: Request, timeout: int | None = None) -> Any:
    """Look up ``urlopen`` on the facade at call time.

    Centralising the lookup in a helper means a test that monkeypatches
    ``dream.agent.urlopen`` is observed on every request, including
    retries, without the backend holding a stale local reference.
    """
    return dream.agent.urlopen(request, timeout=timeout)


def _interruptible_sleep(seconds: float) -> None:
    """Look up ``interruptible_sleep`` on the facade at call time.

    The lookup mirrors :func:`_urlopen`: the helper is read from the
    facade so a test that rewrites ``dream.agent.interruptible_sleep``
    is picked up by the retry loop.
    """
    dream.agent.interruptible_sleep(seconds)


class OpenAIBackend:
    """Client for any endpoint implementing OpenAI's chat-completions API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("DREAM_MODEL", "")
        self.api_key = (
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        )
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.temperature = (
            _resolve_temperature(os.environ.get("DREAM_TEMPERATURE"))
            if temperature is None
            else float(temperature)
        )
        self.reasoning_effort = (
            reasoning_effort if reasoning_effort in {"low", "medium", "high"} else None
        )
        self.user_agent = _resolve_user_agent(
            os.environ.get("DREAM_USER_AGENT"), __version__
        )
        self.max_retries = _resolve_max_retries(os.environ.get("DREAM_MAX_RETRIES"))
        self.retry_backoff_seconds = _resolve_retry_backoff(
            os.environ.get("DREAM_RETRY_BACKOFF_SECONDS")
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Send one chat request, retrying rate limits with backoff.

        Only HTTP 429 is retried: a provider that answers with a rate limit
        is alive and may recover, and each retry sleeps an exponentially
        growing backoff. A provider that hangs is bounded by the per-request
        timeout and reported as a failure rather than retried into the wall
        clock. When every attempt is exhausted the failure message says the
        call was abandoned and how many attempts were made.
        """
        retries = self.max_retries if max_retries is None else max_retries
        for attempt in range(retries + 1):
            status, data = self._attempt_chat(messages, tools)
            if status == 0:
                return data
            rate_limited = status == 429
            if rate_limited and attempt < retries:
                # The OpenAIBackend call is synchronous and has no cancellation
                # token today; the helper is still used so future callers can
                # wire one without re-introducing blocking time.sleep.
                _interruptible_sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            return self._failure(status, _failure_text(data, attempt + 1))

    def _attempt_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> tuple[int, Any]:
        """One request attempt: ``(0, response)`` on success, otherwise
        ``(http_status_or_1, failure_detail)``.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        try:
            with _urlopen(request, timeout=60) as response:  # nosec B310: configured model endpoint
                data = json.loads(response.read().decode("utf-8"))
            message = data["choices"][0]["message"]
            calls = [
                {
                    "id": call.get("id", ""),
                    "name": call["function"]["name"],
                    "arguments": _arguments(call["function"].get("arguments", {})),
                }
                for call in message.get("tool_calls", [])
            ]
            return 0, {"content": message.get("content"), "tool_calls": calls}
        except HTTPError as exc:
            # The body is where the server says what it rejected; keep it.
            return exc.code, _describe_http_error(exc)
        except (URLError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
            return 1, f"{type(exc).__name__}: {exc}"

    def _failure(self, status: int, detail: str) -> dict[str, Any]:
        """Report a failed request without ever echoing raw provider detail."""
        safe_detail = _redact(detail, self.api_key)
        print(f"[provider] Model request failed: {safe_detail}", file=sys.stderr)
        return {
            "content": _provider_failure_reply(status, safe_detail),
            "tool_calls": [],
        }
