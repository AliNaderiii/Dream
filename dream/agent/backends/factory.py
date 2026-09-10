"""Backend factory: select and configure LLM backends from name and environment.

The factory maps provider names (``openai``, ``anthropic``, ``gemini``,
``avalai``, ``deepseek``, ``groq``, ``mistral``, ``together``, ``openrouter``,
``ollama``, ``echo``) to backend instances.

Supports automated multi-provider fallbacks via ``FallbackBackend``.
"""

from __future__ import annotations

import os
from typing import Any

from dream.agent.backends.anthropic import AnthropicBackend
from dream.agent.backends.base import BaseLLMBackend
from dream.agent.backends.echo import EchoBackend
from dream.agent.backends.fallback import FallbackBackend
from dream.agent.backends.gemini import GeminiBackend
from dream.agent.backends.ollama import OllamaBackend
from dream.agent.backends.openai import OpenAIBackend


def _build_single_backend(
    kind: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    **kwargs: Any,
) -> BaseLLMBackend:
    """Instantiate a single backend instance for the given provider kind."""
    selected = kind.lower().strip()

    if selected in ("aval", "avalai"):
        aval_url = base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.avalai.ir/v1"
        aval_key = (
            api_key
            if api_key is not None
            else (os.environ.get("OPENAI_API_KEY") or os.environ.get("AVALAI_API_KEY"))
        )
        return OpenAIBackend(
            model=model,
            base_url=aval_url,
            api_key=aval_key,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    if selected == "openai":
        return OpenAIBackend(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    if selected in ("anthropic", "claude"):
        return AnthropicBackend(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    if selected in ("google", "gemini"):
        oauth = bool(kwargs.get("oauth", False))
        return GeminiBackend(
            model=model,
            credential=api_key,
            base_url=base_url,
            oauth=oauth,
            temperature=temperature,
        )

    if selected == "deepseek":
        ds_key = (
            api_key
            if api_key is not None
            else (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        )
        ds_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        return OpenAIBackend(
            model=model or os.environ.get("DREAM_MODEL", "deepseek-chat"),
            api_key=ds_key,
            base_url=ds_url,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    if selected == "groq":
        groq_key = (
            api_key
            if api_key is not None
            else (os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        )
        groq_url = base_url or os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        return OpenAIBackend(
            model=model or os.environ.get("DREAM_MODEL", "llama-3.3-70b-versatile"),
            api_key=groq_key,
            base_url=groq_url,
            temperature=temperature,
        )

    if selected == "mistral":
        mistral_key = (
            api_key
            if api_key is not None
            else (os.environ.get("MISTRAL_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        )
        mistral_url = base_url or os.environ.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
        return OpenAIBackend(
            model=model or os.environ.get("DREAM_MODEL", "mistral-large-latest"),
            api_key=mistral_key,
            base_url=mistral_url,
            temperature=temperature,
        )

    if selected == "together":
        together_key = (
            api_key
            if api_key is not None
            else (os.environ.get("TOGETHER_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        )
        together_url = base_url or os.environ.get("TOGETHER_BASE_URL", "https://api.together.xyz/v1")
        return OpenAIBackend(
            model=model or os.environ.get("DREAM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
            api_key=together_key,
            base_url=together_url,
            temperature=temperature,
        )

    if selected == "openrouter":
        or_key = (
            api_key
            if api_key is not None
            else (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        )
        or_url = base_url or os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        return OpenAIBackend(
            model=model,
            api_key=or_key,
            base_url=or_url,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    if selected in ("vllm", "llamacpp"):
        return OpenAIBackend(
            model=model,
            api_key=api_key or "",
            base_url=base_url,
            temperature=temperature,
        )

    if selected == "ollama":
        return OllamaBackend(model=model, base_url=base_url)

    if selected == "echo":
        return EchoBackend()

    raise ValueError(f"unknown backend: {selected}")


def build_backend(
    kind: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    fallback: str | list[str] | list[BaseLLMBackend] | None = None,
    **kwargs: Any,
) -> BaseLLMBackend:
    """Select and construct a backend, defaulting to ``DREAM_BACKEND`` or offline echo.

    If ``fallback`` (or env ``DREAM_FALLBACK_BACKEND``) is specified, wraps the
    primary and fallback providers into a :class:`FallbackBackend` cascade.
    """
    selected = (kind or os.environ.get("DREAM_BACKEND", "echo")).lower().strip()
    primary = _build_single_backend(
        selected,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        **kwargs,
    )

    fallback_spec = fallback or os.environ.get("DREAM_FALLBACK_BACKEND")
    if not fallback_spec:
        return primary

    fallback_backends: list[BaseLLMBackend] = [primary]
    if isinstance(fallback_spec, str):
        fallback_names = [name.strip() for name in fallback_spec.split(",") if name.strip()]
        for fname in fallback_names:
            if fname.lower() != selected:
                fallback_backends.append(_build_single_backend(fname))
    elif isinstance(fallback_spec, list):
        for item in fallback_spec:
            if isinstance(item, BaseLLMBackend):
                fallback_backends.append(item)
            elif isinstance(item, str) and item.strip().lower() != selected:
                fallback_backends.append(_build_single_backend(item.strip()))

    if len(fallback_backends) > 1:
        return FallbackBackend(fallback_backends)
    return primary
