"""Dream: a personal assistant with first-class Persian language support."""

from __future__ import annotations

from dream.agent import (
    ApprovalPolicy,
    Dream,
    EchoBackend,
    OllamaBackend,
    OpenAIBackend,
    Turn,
    build_backend,
    cli_approver,
)
from dream.memory import KINDS, Memory, MemoryStore, normalize_fa
from dream.tools import REGISTRY, anthropic_schemas, execute, openai_schemas, tool

__version__ = "0.1.0"

__all__ = [
    "ApprovalPolicy",
    "Dream",
    "EchoBackend",
    "KINDS",
    "Memory",
    "MemoryStore",
    "OllamaBackend",
    "OpenAIBackend",
    "REGISTRY",
    "Turn",
    "anthropic_schemas",
    "build_backend",
    "cli_approver",
    "execute",
    "normalize_fa",
    "openai_schemas",
    "tool",
    "__version__",
]
