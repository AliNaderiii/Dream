"""Fallback / Cascade LLM Backend for Dream.

Provides automated multi-provider failover. When a primary provider hits
rate limits (429), server errors (5xx), or connectivity outages, the
fallback backend transparently cascades to the next configured provider
in the chain.
"""

from __future__ import annotations

import logging
from typing import Any

from dream.agent.backends.base import BaseLLMBackend

log = logging.getLogger("dream.agent.backends.fallback")


class FallbackBackend(BaseLLMBackend):
    """Cascading backend that tries each backend in order until one succeeds."""

    def __init__(self, backends: list[BaseLLMBackend]) -> None:
        if not backends:
            raise ValueError("FallbackBackend requires at least one backend")
        self.backends = list(backends)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Attempt chat across the fallback chain in order."""
        last_response: dict[str, Any] = {"content": None, "tool_calls": []}
        for i, backend in enumerate(self.backends):
            try:
                response = backend.chat(messages, tools=tools, max_retries=max_retries)
                content = response.get("content")
                tool_calls = response.get("tool_calls")
                # If tool_calls or non-failure content is present, return it
                is_failure_reply = (
                    isinstance(content, str)
                    and content.startswith("The provider request failed")
                )
                if (tool_calls or content) and not is_failure_reply:
                    return response
                last_response = response
                if i < len(self.backends) - 1:
                    log.warning(
                        "Primary backend %s returned failure; cascading to next backend %s",
                        type(backend).__name__,
                        type(self.backends[i + 1]).__name__,
                    )
            except Exception as exc:
                log.warning(
                    "Backend %s raised exception %s; cascading to next backend",
                    type(backend).__name__,
                    exc,
                )
                if i == len(self.backends) - 1:
                    raise
        return last_response
