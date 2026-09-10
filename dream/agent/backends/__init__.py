"""LLM backends for the Dream agent.

The backend surface is intentionally minimal: every backend exposes a
``chat(messages, tools=None)`` method that returns a dict with two
keys, ``content`` (the assistant text) and ``tool_calls`` (a list of
``{id, name, arguments}`` dicts). A :class:`Dream` instance never
inspects the backend beyond that contract, so a new provider is one
file plus a registration in :mod:`dream.agent.backends.factory`.
"""

from __future__ import annotations

from dream.agent.backends.echo import EchoBackend
from dream.agent.backends.factory import build_backend
from dream.agent.backends.ollama import OllamaBackend
from dream.agent.backends.openai import OpenAIBackend

__all__ = [
    "EchoBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "build_backend",
]
