"""EchoBackend: deterministic offline backend for tests and local demos.

The echo backend never opens a network socket. It pattern-matches the
most recent user message and either:

* echoes it back (no tool calls), or
* emits a single ``get_datetime`` tool call when the message mentions
  time or date (English: "time", "date"; Persian: "ساعت", "زمان"), or
* emits a single ``calculate`` tool call when the message contains a
  recognisable arithmetic expression (the :data:`_MATH` regex).

The math expression is filtered to digits, ``+ - * / × ÷`` and
whitespace, then handed to the ``calculate`` tool so the real
evaluation lives in a tested, deterministic place. The Persian and
Arabic digit ranges (U+0660..U+0669, U+06F0..U+06F9) are accepted
in the input so a user typing «۱۲ × ۳» is recognised the same way
as ``12 * 3``.

Echo is the *only* backend that is guaranteed to run with no API key
and no network: it is the default when ``DREAM_BACKEND`` is unset, and
it is what ``dream --demo`` uses to render the README transcript.
"""

from __future__ import annotations

import re
from typing import Any

from dream.agent.backends.base import BaseLLMBackend


class EchoBackend(BaseLLMBackend):
    """Offline deterministic backend used for tests and local demos."""

    _MATH = re.compile(r"[0-9۰-۹٠-٩][0-9۰-۹٠-٩\s+\-*/×÷().]*[+\-*/×÷]")

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Return one deterministic response for the latest user turn.

        If the most recent message is a tool result the backend echoes it
        back as the assistant text, so a tool call in a previous turn
        yields a readable next turn without a real model.
        """
        del tools, max_retries
        if messages and messages[-1].get("role") == "tool":
            result = messages[-1].get("content", "")
            return {"content": f"Result: {result}", "tool_calls": []}
        text = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        lowered = text.lower()
        if any(word in lowered for word in ("time", "date", "ساعت", "زمان")):
            return {
                "content": None,
                "tool_calls": [
                    {"id": "echo-time", "name": "get_datetime", "arguments": {}}
                ],
            }
        if self._MATH.search(text):
            expression = re.sub(r"[^0-9۰-۹٠-٩\s+\-*/×÷().]", "", text).strip()
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "echo-calculate",
                        "name": "calculate",
                        "arguments": {"expression": expression},
                    }
                ],
            }
        return {"content": f"Echo: {text}", "tool_calls": []}
