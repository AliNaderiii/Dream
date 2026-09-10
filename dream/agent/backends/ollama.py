"""Ollama backend — OpenAI-compatible client pointed at a local Ollama server.

Ollama speaks the OpenAI chat-completions protocol, so this class only
adapts the host URL and clears the API key (Ollama's local server
ignores the header anyway, but sending ``Bearer ""`` is friendlier to
the request log). The default model is ``llama3.2`` so a fresh install
works out of the box; operators override with ``DREAM_MODEL``.
"""

from __future__ import annotations

import os

from dream.agent.backends.openai import OpenAIBackend


class OllamaBackend(OpenAIBackend):
    """OpenAI-compatible client pointed at a local Ollama server."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        host = base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        super().__init__(
            model=model or os.environ.get("DREAM_MODEL", "llama3.2"),
            api_key="",
            base_url=f"{host.rstrip('/')}" + "/v1",
        )
