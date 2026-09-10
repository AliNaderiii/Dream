"""Tool execution dispatcher with security floor scanning and approval enforcement."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from dream.security.blocklist import scan as _floor_scan
from dream.security.engine import SHELL_COMMAND_TOOLS as _FLOOR_COMMAND_TOOLS
from dream.tools.base import REGISTRY, Tool

logger = logging.getLogger(__name__)


def _failure_payload(error_type: str, message: str) -> dict[str, Any]:
    """Build an error payload that cannot be mistaken for a result.

    The agent feeds this string straight back to the model. A bare
    ``{"error": ...}`` is easy for a small model to skim past and narrate as a
    success, so every failure carries an explicit ``"status": "error"`` and a
    message that starts with ``Tool call failed:``.
    """
    return {"status": "error", "error": {"type": error_type, "message": message}}


def execute(
    name: str,
    arguments: dict[str, Any],
    *,
    approved: bool = False,
    registry: Mapping[str, Tool] | None = None,
) -> str:
    """Run a registered tool and JSON-encode its result or error.

    Dangerous tools remain blocked unless an approval gate explicitly passes
    ``approved=True``. This keeps direct callers fail-closed while allowing the
    agent runtime to enforce a human decision on its execution path.

    ``registry`` dispatches against a private table instead of the process
    global. A tool absent from that table is reported as unknown, which is the
    correct answer for a subagent: the capability does not exist for it.
    """
    registered = (REGISTRY if registry is None else registry).get(name)
    if registered is None:
        return json.dumps(
            _failure_payload("unknown_tool", f"Tool call failed: unknown tool: {name}"),
            ensure_ascii=False,
        )
    # L3 security floor: evaluated BEFORE the approval check and impossible
    # to override with ``approved=True`` — a blocklisted command never runs,
    # no matter who called or what flag they carry.
    if name in _FLOOR_COMMAND_TOOLS:
        floor_match = _floor_scan(str(arguments.get("command", "")))
        if floor_match is not None:
            return json.dumps(
                _failure_payload(
                    "security_floor_blocked",
                    f"Tool call failed: {floor_match.refusal}",
                ),
                ensure_ascii=False,
            )
    if registered.risk == "dangerous" and not approved:
        return json.dumps(
            _failure_payload(
                "approval_required",
                f"Tool call failed: {name} requires human approval and none was given",
            ),
            ensure_ascii=False,
        )
    if registered.risk == "guarded":
        logger.info("executing guarded tool: %s", name)
    try:
        result = registered.function(**arguments)
        return json.dumps({"status": "ok", "result": result}, ensure_ascii=False)
    except Exception as exc:  # Tool boundaries return data, never leak exceptions.
        return json.dumps(
            _failure_payload(
                type(exc).__name__,
                f"Tool call failed: {name}() raised {type(exc).__name__}: {exc}",
            ),
            ensure_ascii=False,
        )
