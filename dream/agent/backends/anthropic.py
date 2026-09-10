"""Anthropic Claude backend — native Messages API adapter for Dream.

Communicates with ``https://api.anthropic.com/v1/messages`` using the
standard library urllib client. Handles:
- Translating system messages into the top-level ``system`` prompt.
- Converting tool schemas into Anthropic's ``input_schema`` format.
- Parsing ``tool_use`` content blocks into standard Dream ``tool_calls``.
- Handling Claude thinking/reasoning budgets.
- Rate-limit retry loops on 429 and 529 with exponential backoff.
- Safe error logging and API key redaction.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
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


class AnthropicBackend(BaseLLMBackend):
    """Native backend adapter for Anthropic Claude (Messages API)."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("DREAM_MODEL", "claude-sonnet-4-20250514")
        self.api_key = (
            api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.base_url = (
            base_url or os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
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
        """Send one Messages API request, retrying rate limits and overloads with backoff."""
        retries = self.max_retries if max_retries is None else max_retries
        for attempt in range(retries + 1):
            status, data = self._attempt_chat(messages, tools)
            if status == 0:
                return data
            rate_limited = status in (429, 529)
            if rate_limited and attempt < retries:
                _interruptible_sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            return self._failure(status, _failure_text(data, attempt + 1))

    def _attempt_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> tuple[int, Any]:
        system_parts: list[str] = []
        conversation: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                if content:
                    system_parts.append(str(content))
            elif role in {"user", "assistant"}:
                conversation.append({"role": role, "content": str(content or "")})
            elif role == "tool":
                tool_id = str(msg.get("tool_call_id") or "")
                conversation.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": str(content or ""),
                        }
                    ],
                })

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": conversation,
            "temperature": self.temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        if self.reasoning_effort:
            budget_map = {"low": 1024, "medium": 4096, "high": 8192}
            budget = budget_map.get(self.reasoning_effort, 1024)
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
            payload["max_tokens"] = budget + 4096
            payload.pop("temperature", None)

        if tools:
            anthropic_tools: list[dict[str, Any]] = []
            for t in tools:
                func = t.get("function", t)
                name = func.get("name")
                desc = func.get("description", "")
                schema = (
                    func.get("parameters")
                    or func.get("input_schema")
                    or {"type": "object", "properties": {}}
                )
                anthropic_tools.append({
                    "name": name,
                    "description": desc,
                    "input_schema": schema,
                })
            payload["tools"] = anthropic_tools

        request = Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        try:
            with _urlopen(request, timeout=60) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8"))
            blocks = data.get("content", [])
            text_blocks: list[str] = []
            calls: list[dict[str, Any]] = []
            for block in blocks:
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype == "text":
                        text_blocks.append(str(block.get("text") or ""))
                    elif btype == "tool_use":
                        inp = block.get("input")
                        calls.append({
                            "id": str(block.get("id") or ""),
                            "name": str(block.get("name") or ""),
                            "arguments": inp if isinstance(inp, dict) else {},
                        })
            content_str = "".join(text_blocks).strip() or None
            return 0, {"content": content_str, "tool_calls": calls}
        except HTTPError as exc:
            return exc.code, _describe_http_error(exc)
        except (URLError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
            return 1, f"{type(exc).__name__}: {exc}"

    def _failure(self, status: int, detail: str) -> dict[str, Any]:
        safe_detail = _redact(detail, self.api_key)
        print(f"[provider:anthropic] Model request failed: {safe_detail}", file=sys.stderr)
        return {
            "content": _provider_failure_reply(status, safe_detail),
            "tool_calls": [],
        }
