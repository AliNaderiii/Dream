"""LLM backends for the Dream agent.

The backend surface is unified across all providers: every backend exposes a
``chat(messages, tools=None)`` method returning ``{"content": ..., "tool_calls": [...]}``.
"""

from __future__ import annotations

from dream.agent.backends.anthropic import AnthropicBackend
from dream.agent.backends.base import BaseLLMBackend
from dream.agent.backends.echo import EchoBackend
from dream.agent.backends.factory import build_backend
from dream.agent.backends.fallback import FallbackBackend
from dream.agent.backends.gemini import GeminiBackend, GoogleBackend
from dream.agent.backends.ollama import OllamaBackend
from dream.agent.backends.openai import OpenAIBackend

__all__ = [
    "AnthropicBackend",
    "BaseLLMBackend",
    "EchoBackend",
    "FallbackBackend",
    "GeminiBackend",
    "GoogleBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "build_backend",
]
