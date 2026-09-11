"""LLM Tool bindings for Layered Context Hierarchy manipulation."""

from __future__ import annotations

from typing import Any

from dream.context.engine import ContextEngine

_GLOBAL_CONTEXT_ENGINE: ContextEngine | None = None


def get_global_context_engine() -> ContextEngine:
    """Get or create singleton ContextEngine."""
    global _GLOBAL_CONTEXT_ENGINE
    if _GLOBAL_CONTEXT_ENGINE is None:
        _GLOBAL_CONTEXT_ENGINE = ContextEngine()
    return _GLOBAL_CONTEXT_ENGINE


def reset_global_context_engine() -> None:
    """Reset singleton for tests."""
    global _GLOBAL_CONTEXT_ENGINE
    _GLOBAL_CONTEXT_ENGINE = None


def context_get_tier(tier: str = "soul") -> dict[str, Any]:
    """Retrieve content and metadata of a specific context tier (soul, agents, user, memory)."""
    engine = get_global_context_engine()
    cf = engine.get_tier(tier)
    return cf.to_dict()


def context_update_tier(tier: str, content: str) -> dict[str, Any]:
    """Update content of a specific context tier file (soul, agents, user, memory)."""
    engine = get_global_context_engine()
    success = engine.update_tier(tier, content)
    cf = engine.get_tier(tier)
    data = cf.to_dict()
    data["success"] = success
    return data


def context_get_budget_report() -> dict[str, Any]:
    """Retrieve current character/token allocation breakdown across all context tiers."""
    engine = get_global_context_engine()
    return engine.get_budget_report()


def context_assemble_prompt() -> dict[str, Any]:
    """Assemble all 4 context tiers into a prioritized system prompt context block."""
    engine = get_global_context_engine()
    assembly = engine.assemble_context()
    return assembly.to_dict()


def context_reload_all() -> dict[str, Any]:
    """Force reload all context files from disk and refresh in-memory cache."""
    engine = get_global_context_engine()
    return engine.reload_all()


def get_context_tools() -> list[Any]:
    """Return list of context hierarchy tool functions for agent binding."""
    return [
        context_get_tier,
        context_update_tier,
        context_get_budget_report,
        context_assemble_prompt,
        context_reload_all,
    ]
