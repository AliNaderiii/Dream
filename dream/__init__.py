"""Dream: a personal assistant with first-class Persian language support."""

from __future__ import annotations

# The single runtime source of the product version; keep it identical to
# ``pyproject.toml`` (see docs/dev/how-to/build-and-sign-installers.md). It is
# bound *before* the submodule imports below on purpose: ``dream.agent`` reads
# it for the default User-Agent while this package is still initialising, and
# ``from dream import __version__`` there would otherwise be a circular import.
__version__ = "0.4.6"

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
from dream.extraction import ExtractedFact, ExtractionResult, extract_facts
from dream.memory import KINDS, Memory, MemoryStore, normalize_fa
from dream.normalization import normalize_importance, normalize_kind
from dream.tools import REGISTRY, anthropic_schemas, execute, openai_schemas, tool

__all__ = [
    "ApprovalPolicy",
    "Dream",
    "EchoBackend",
    "ExtractedFact",
    "ExtractionResult",
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
    "extract_facts",
    "normalize_fa",
    "normalize_importance",
    "normalize_kind",
    "openai_schemas",
    "tool",
    "__version__",
]
