"""Runtime adapters: bounded probe, list_models, and chat with parser apply."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dream.providerhubs.parsers import parse_tool_calls
from dream.providerhubs.types import (
    BACKOFF_BASE_SECONDS,
    CHAT_TIMEOUT_SECONDS,
    MAX_RETRIES,
    PROBE_TIMEOUT_SECONDS,
    RUNTIME_SPECS,
)

Opener = Callable[..., Any]


class RuntimeAdapter:
    """One local serving stack behind a compatible ``/v1`` endpoint."""

    def __init__(
        self,
        runtime_id: str,
        *,
        endpoint: str | None = None,
        opener: Opener = urlopen,
        timeout: float = PROBE_TIMEOUT_SECONDS,
    ) -> None:
        if runtime_id not in RUNTIME_SPECS:
            raise ValueError(f"unknown runtime: {runtime_id}")
        spec = RUNTIME_SPECS[runtime_id]
        self.runtime_id = runtime_id
        self.spec = spec
        self.endpoint = (endpoint or spec["endpoint"]).rstrip("/")
        self.parser = str(spec["parser"])
        self._opener = opener
        self.timeout = timeout

    def configured_from_env(self) -> bool:
        backend = (os.environ.get("DREAM_BACKEND") or "").strip().lower()
        if backend in self.spec["backend_names"]:
            return True
        for key in self.spec["env_keys"]:
            if (os.environ.get(key) or "").strip():
                return True
        return False

    def env_endpoint(self) -> str:
        for key in self.spec["env_keys"]:
            value = (os.environ.get(key) or "").strip()
            if value:
                return value.rstrip("/")
        return self.endpoint

    def health(self) -> dict[str, Any]:
        """One cheap GET. Never attaches credentials."""
        started = time.monotonic()
        ok, _detail, status = self._request("GET", "/models", timeout=self.timeout)
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        result = {
            "ok": ok,
            "health": "healthy" if ok else "down",
            "latency_ms": latency_ms,
            "http_status": status,
        }
        return result

    def list_models(self) -> list[str]:
        ok, payload, _status = self._request("GET", "/models", timeout=self.timeout)
        if not ok:
            return []
        return _parse_models(payload)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": "local",
            "messages": messages,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        ok, payload, _status = self._request(
            "POST",
            "/chat/completions",
            data=body,
            timeout=CHAT_TIMEOUT_SECONDS,
        )
        if not ok:
            return {"content": "", "tool_calls": [], "ok": False}
        text = _content_text(payload)
        calls = parse_tool_calls(text, self.parser, payload)
        return {"content": text, "tool_calls": calls, "ok": True, "payload": payload}

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        timeout: float,
    ) -> tuple[bool, Any, int]:
        url = f"{self.endpoint}{path}"
        encoded = None if data is None else json.dumps(data).encode("utf-8")
        headers = {"Accept": "application/json"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        last_status = 0
        for attempt in range(MAX_RETRIES + 1):
            request = Request(url, data=encoded, headers=headers, method=method)
            try:
                with self._opener(request, timeout=timeout) as response:
                    raw = response.read()
                    status = int(getattr(response, "status", 200) or 200)
                    payload = _decode(raw)
                    return True, payload, status
            except HTTPError as exc:
                last_status = int(exc.code)
                if exc.code == 429 and attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
                    continue
                return False, None, last_status
            except (URLError, TimeoutError, OSError, ValueError):
                return False, None, 0
        return False, None, last_status


def _decode(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}


def _parse_models(payload: Any) -> list[str]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data") or payload.get("models") or []
    else:
        rows = []
    models: list[str] = []
    for row in rows:
        if isinstance(row, str) and row.strip():
            models.append(row.strip())
        elif isinstance(row, dict):
            ident = row.get("id") or row.get("name") or row.get("model")
            if isinstance(ident, str) and ident.strip():
                models.append(ident.strip().removeprefix("models/"))
    return list(dict.fromkeys(models))


def _content_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        text = choices[0].get("text")
        if isinstance(text, str):
            return text
    content = payload.get("content")
    return content if isinstance(content, str) else ""
