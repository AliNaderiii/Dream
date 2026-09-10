"""Base interface and protocol for Dream LLM backends.

Every backend exposes a ``chat(messages, tools=None)`` method returning
a dict with ``content`` (str | None) and ``tool_calls`` (list of dicts
with ``id``, ``name``, ``arguments``).
"""

from __future__ import annotations

import abc
from typing import Any


class BaseLLMBackend(abc.ABC):
    """Abstract interface for all LLM backends in Dream."""

    @abc.abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Execute a single conversational turn.

        Args:
            messages: OpenAI-format list of messages (role, content, etc.).
            tools: OpenAI-format tool schemas list or None.
            max_retries: Override for maximum rate-limit retry attempts.

        Returns:
            dict with:
                "content": str | None (the assistant text response)
                "tool_calls": list[dict[str, Any]] with keys:
                    "id": str, "name": str, "arguments": dict[str, Any]
        """
        ...
