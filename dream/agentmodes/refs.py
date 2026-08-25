"""Chat references: @file, #conversation, /commands, !shell. Persian-aware."""

from __future__ import annotations

import re
from typing import Any

from dream.agentmodes.errors import AgentModeError

_FILE = re.compile(r"@([^\s@#/!]{1,240})")
_CONV = re.compile(r"#([A-Za-z0-9_-]{1,80})")
_CMD = re.compile(r"(?:^|\s)/([A-Za-z0-9_\u0600-\u06ff-]{1,40})")
_SHELL = re.compile(r"(?:^|\s)!([^\n]{1,500})")

COMMAND_PALETTE: tuple[dict[str, str], ...] = (
    {"name": "plan", "title": "/plan", "summary": "Plan first, execute only after continue"},
    {"name": "goal", "title": "/goal", "summary": "Capture an objective and acceptance criteria"},
    {"name": "stop", "title": "/stop", "summary": "Cancel the running turn (live server state)"},
    {"name": "status", "title": "/status", "summary": "Live subagent and mode status"},
    {
        "name": "barnameh",
        "title": "/\u0628\u0631\u0646\u0627\u0645\u0647",
        "summary": "Persian alias for /plan",
    },
    {
        "name": "hadaf",
        "title": "/\u0647\u062f\u0641",
        "summary": "Persian alias for /goal",
    },
    {
        "name": "tavaghof",
        "title": "/\u062a\u0648\u0642\u0641",
        "summary": "Persian alias for /stop",
    },
)


def parse_references(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or len(text) > 20_000:
        raise AgentModeError("text must be a string of at most 20000 characters")
    files = _FILE.findall(text)
    conversations = _CONV.findall(text)
    commands = _CMD.findall(text)
    shells = [item.strip() for item in _SHELL.findall(text) if item.strip()]
    return {
        "files": files,
        "conversations": conversations,
        "commands": commands,
        "shell": shells,
    }


def command_palette(query: str = "") -> dict[str, Any]:
    needle = (query or "").strip().lstrip("/").lower()
    items = [
        item
        for item in COMMAND_PALETTE
        if not needle
        or needle in item["name"]
        or needle in item["title"].lower()
        or needle in item["summary"].lower()
    ]
    return {"commands": items, "count": len(items)}
