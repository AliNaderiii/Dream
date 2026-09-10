"""Schema export helpers for OpenAI, Anthropic, and Google Gemini formats."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dream.tools.base import REGISTRY, Tool


def openai_schemas(registry: Mapping[str, Tool] | None = None) -> list[dict[str, Any]]:
    """Return registered tools in OpenAI's function-tool format.

    ``registry`` narrows the export to a private table. Subagents are granted a
    subset of the tools their parent holds, and the model must not be told
    about capabilities it will be refused, so the schema list and the dispatch
    table have to come from the same mapping.
    """
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.schema},
        }
        for t in (REGISTRY if registry is None else registry).values()
    ]


def anthropic_schemas(registry: Mapping[str, Tool] | None = None) -> list[dict[str, Any]]:
    """Return registered tools in Anthropic's tool format."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema}
        for t in (REGISTRY if registry is None else registry).values()
    ]


def gemini_schemas(registry: Mapping[str, Tool] | None = None) -> list[dict[str, Any]]:
    """Return registered tools in Google Gemini's function declarations format."""
    return [
        {
            "function_declarations": [
                {"name": t.name, "description": t.description, "parameters": t.schema}
                for t in (REGISTRY if registry is None else registry).values()
            ]
        }
    ]
