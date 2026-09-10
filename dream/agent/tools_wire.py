"""Tool-call wire conversion and the CLI approval callback.

The :func:`_wire_tool_calls` helper bridges Dream's internal tool-call
shape (``{id, name, arguments: dict}``) and the chat-completions wire
format (``{id, type, function: {name, arguments: "<json>"}}``). Replaying
the internal shape in history makes every request after the first tool
call a 400, which is why the first turn works and the second does not.
The conversion lives here so the backend and the turn loop can both
import it without creating a cycle through the Dream class.

The :func:`cli_approver` callback is the *interactive* approval used
when no other approver is configured. It is intentionally minimal: any
input other than ``y`` or ``yes`` (after a case-insensitive strip) is
a denial, and an interrupted prompt is also a denial. There is no
retry: a denied dangerous tool stays denied, the same way the
:class:`ApprovalPolicy` denies it.
"""

from __future__ import annotations

import json
from typing import Any

from dream.agent.http_utils import _arguments


def _wire_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Dream's internal tool calls to chat-completions wire format.

    Internally a call is ``{"id", "name", "arguments": {...}}``. The API expects
    ``{"id", "type": "function", "function": {"name", "arguments": "<json>"}}``.
    Replaying the internal shape in history makes every request after the first
    tool call a 400, which is why the first turn works and the second does not.
    """
    wire: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        nested = call.get("function")
        source = nested if isinstance(nested, dict) else call
        wire.append(
            {
                "id": str(call.get("id") or f"call_{index}"),
                "type": "function",
                "function": {
                    "name": str(source.get("name", "")),
                    "arguments": json.dumps(
                        _arguments(source.get("arguments", {})), ensure_ascii=False
                    ),
                },
            }
        )
    return wire


def cli_approver(tool_name: str, arguments: dict[str, Any]) -> bool:
    """Ask on the terminal, treating interrupted input as a denial."""
    try:
        answer = input(
            f"Allow {tool_name}({json.dumps(arguments, ensure_ascii=False)})? [y/N] "
        )
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in {"y", "yes"}
