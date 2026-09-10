"""Backend factory: select a backend from a name and the environment.

The factory is the single place that maps a name (``openai``, ``aval``,
``ollama``, ``echo``) to a class. ``DREAM_BACKEND`` defaults to ``echo``
so a fresh install runs with no API key and no network. An unknown
name raises :class:`ValueError` so a misconfiguration is loud, not
silent.
"""

from __future__ import annotations

import os

from dream.agent.backends.echo import EchoBackend
from dream.agent.backends.ollama import OllamaBackend
from dream.agent.backends.openai import OpenAIBackend


def build_backend(
    kind: str | None = None,
) -> OpenAIBackend | OllamaBackend | EchoBackend:
    """Select a backend, defaulting to ``DREAM_BACKEND`` or offline echo."""
    selected = (kind or os.environ.get("DREAM_BACKEND", "echo")).lower()
    if selected in ("aval", "avalai"):
        # Aval AI is an OpenAI-compatible endpoint (see ``dream/router.py``
        # and the Aval section of ``.env.example``). The base URL and key come
        # from the same environment names the router reads: ``OPENAI_BASE_URL``
        # wins, the documented Aval host is the fallback, and the key is
        # ``OPENAI_API_KEY`` or the Aval-specific ``AVALAI_API_KEY``.
        return OpenAIBackend(
            base_url=os.environ.get("OPENAI_BASE_URL") or "https://api.avalai.ir/v1",
            api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("AVALAI_API_KEY"),
        )
    if selected == "openai":
        return OpenAIBackend()
    if selected == "ollama":
        return OllamaBackend()
    if selected == "echo":
        return EchoBackend()
    raise ValueError(f"unknown backend: {selected}")
