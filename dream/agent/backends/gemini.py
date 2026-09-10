"""Google Gemini backend — native Generative Language API adapter for Dream.

Communicates with ``https://generativelanguage.googleapis.com/v1beta`` using
the standard library urllib client. Handles:
- Translating system messages into ``system_instruction``.
- Translating tools into ``function_declarations``.
- Parsing ``functionCall`` parts into standard Dream ``tool_calls``.
- Supporting both API key query authentication and OAuth Bearer tokens.
- Rate-limit retry loops with backoff.
- Safe error logging and credential redaction.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request

import dream.agent
from dream import __version__
from dream.agent.backends.base import BaseLLMBackend
from dream.agent.env_config import (
    _resolve_max_retries,
    _resolve_retry_backoff,
    _resolve_temperature,
)
from dream.agent.http_utils import (
    _describe_http_error,
    _failure_text,
    _provider_failure_reply,
    _redact,
)
from dream.agent.user_agent import _resolve_user_agent


def _urlopen(request: Request, timeout: int | None = None) -> Any:
    return dream.agent.urlopen(request, timeout=timeout)


def _interruptible_sleep(seconds: float) -> None:
    dream.agent.interruptible_sleep(seconds)


class GeminiBackend(BaseLLMBackend):
    """Native backend adapter for Google Gemini (Generative Language API)."""

    def __init__(
        self,
        model: str | None = None,
        credential: str | None = None,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        oauth: bool = False,
        temperature: float | None = None,
    ) -> None:
        self.model = model or os.environ.get("DREAM_MODEL", "gemini-2.5-flash")
        raw_key = api_key or credential
        fallback_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
        self.credential = raw_key if raw_key is not None else fallback_key
        self.api_key = self.credential
        default_base = "https://generativelanguage.googleapis.com/v1beta"
        self.base_url = (base_url or os.environ.get("GEMINI_BASE_URL", default_base)).rstrip("/")
        self.oauth = oauth
        self.temperature = (
            _resolve_temperature(os.environ.get("DREAM_TEMPERATURE"))
            if temperature is None
            else float(temperature)
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
        """Send one generateContent request, retrying rate limits with backoff."""
        retries = self.max_retries if max_retries is None else max_retries
        for attempt in range(retries + 1):
            status, data = self._attempt_chat(messages, tools)
            if status == 0:
                return data
            rate_limited = status in (429, 503)
            if rate_limited and attempt < retries:
                _interruptible_sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            return self._failure(status, _failure_text(data, attempt + 1))

    def _attempt_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> tuple[int, Any]:
        contents: list[dict[str, Any]] = []
        system_texts: list[str] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                if content:
                    system_texts.append(str(content))
            elif role in {"user", "assistant"}:
                g_role = "model" if role == "assistant" else "user"
                contents.append({
                    "role": g_role,
                    "parts": [{"text": str(content or "")}],
                })
            elif role == "tool":
                tool_name = str(msg.get("name") or "tool")
                contents.append({
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": tool_name,
                                "response": {"name": tool_name, "content": str(content or "")},
                            }
                        }
                    ],
                })

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
            },
        }
        if system_texts:
            payload["system_instruction"] = {
                "parts": [{"text": "\n\n".join(system_texts)}]
            }

        if tools:
            declarations: list[dict[str, Any]] = []
            for t in tools:
                func = t.get("function", t)
                declarations.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters") or {"type": "object", "properties": {}},
                })
            payload["tools"] = [{"function_declarations": declarations}]

        query = "" if self.oauth else f"?{urlencode({'key': self.credential})}"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.oauth:
            headers["Authorization"] = f"Bearer {self.credential}"

        model_path = quote(self.model, safe="")
        url = f"{self.base_url}/models/{model_path}:generateContent{query}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with _urlopen(request, timeout=60) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                return 0, {"content": "", "tool_calls": []}
            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts: list[str] = []
            calls: list[dict[str, Any]] = []
            for i, part in enumerate(parts):
                if isinstance(part, dict):
                    if "text" in part:
                        text_parts.append(str(part["text"]))
                    elif "functionCall" in part:
                        fn = part["functionCall"]
                        calls.append({
                            "id": f"call_gemini_{i}",
                            "name": str(fn.get("name") or ""),
                            "arguments": fn.get("args") or {},
                        })
            content_str = "".join(text_parts).strip() or None
            return 0, {"content": content_str, "tool_calls": calls}
        except HTTPError as exc:
            return exc.code, _describe_http_error(exc)
        except (URLError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
            return 1, f"{type(exc).__name__}: {exc}"

    def _failure(self, status: int, detail: str) -> dict[str, Any]:
        safe_detail = _redact(detail, self.credential)
        print(f"[provider:gemini] Model request failed: {safe_detail}", file=sys.stderr)
        return {
            "content": _provider_failure_reply(status, safe_detail),
            "tool_calls": [],
        }


# Backward-compatible alias for existing callers
GoogleBackend = GeminiBackend
