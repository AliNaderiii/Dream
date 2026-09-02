"""Centralized input validation limits and helpers for Dream tools (SEC-05).

Defines strict boundary limits for tool parameters (text, code, paths, URLs,
queries, IDs, lists, mappings, nesting depth, serialized size, and numeric ranges).
"""

from __future__ import annotations

MAX_TOOL_INPUT_CHARS: dict[str, int] = {
    "text": 16_000,
    "code": 32_000,
    "path": 4_096,
    "url": 2_048,
    "query": 1_000,
    "id": 256,
    "default": 8_000,
}

MAX_LIST_ITEMS: int = 500
MAX_MAPPING_KEYS: int = 256
MAX_NESTING_DEPTH: int = 10
MAX_SERIALIZED_INPUT_SIZE: int = 65_536

NUMERIC_RANGES: dict[str, tuple[int | float, int | float]] = {
    "timeout": (1, 300),
    "repeat_days": (1, 3650),
    "repeat_months": (1, 120),
}


def get_parameter_category(tool_name: str, param_name: str) -> str:
    """Determine the validation category for a tool parameter based on name/context.

    Categories:
    - path: filesystem paths (e.g. filename)
    - url: web addresses (e.g. address)
    - query: search terms, expressions, dates (e.g. query, expression, date)
    - code: script commands, bodies (e.g. command, body)
    - id: identifiers, names, zones (e.g. name, proposal_id, timezone_name, to)
    - text: general text, notes, subjects (e.g. content, subject, text, description)
    - default: fallback category
    """
    del tool_name
    if param_name in {"filename", "path"}:
        return "path"
    if param_name in {"address", "url"}:
        return "url"
    if param_name in {"query", "expression", "date"}:
        return "query"
    if param_name in {"command", "body"}:
        return "code"
    if param_name in {"name", "proposal_id", "timezone_name", "to"}:
        return "id"
    if param_name in {"content", "subject", "text", "description"}:
        return "text"
    return "default"
