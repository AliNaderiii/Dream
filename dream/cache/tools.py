"""LLM Tool bindings for Semantic Caching, Speculative Execution, and Token Economics."""

from __future__ import annotations

from typing import Any

from dream.cache.engine import CacheEngine

_GLOBAL_CACHE_ENGINE: CacheEngine | None = None


def get_global_cache_engine() -> CacheEngine:
    """Get or initialize singleton CacheEngine."""
    global _GLOBAL_CACHE_ENGINE
    if _GLOBAL_CACHE_ENGINE is None:
        _GLOBAL_CACHE_ENGINE = CacheEngine()
    return _GLOBAL_CACHE_ENGINE


def reset_global_cache_engine() -> None:
    """Reset CacheEngine singleton instance."""
    global _GLOBAL_CACHE_ENGINE
    _GLOBAL_CACHE_ENGINE = None


def cache_lookup_query(
    query: str,
    similarity_threshold: float = 0.88,
) -> dict[str, Any]:
    """Check if query exists in L1 exact or L2 semantic cache to bypass LLM generation."""
    engine = get_global_cache_engine()
    entry = engine.query(query, similarity_threshold=similarity_threshold)
    if entry:
        return {
            "hit": True,
            "tier": entry.tier.value,
            "similarity_score": round(entry.similarity_score, 3),
            "response": entry.response,
            "tokens_saved": entry.tokens_saved,
        }
    return {"hit": False, "response": None}


def cache_store_entry(
    query: str,
    response: str,
    ttl_seconds: float = 3600.0,
    tokens_saved: int = 0,
) -> dict[str, Any]:
    """Store query and response pair in the semantic cache with TTL."""
    engine = get_global_cache_engine()
    entry = engine.store(
        prompt=query,
        response=response,
        ttl_seconds=ttl_seconds,
        tokens_saved=tokens_saved,
    )
    return {"success": True, "entry_id": entry.id, "tier": entry.tier.value}


def cache_predict_tool(
    user_input: str,
) -> dict[str, Any]:
    """Evaluate speculative pre-fetching pattern on user input before model invocation."""
    engine = get_global_cache_engine()
    pred = engine.predict_speculative_tool(user_input)
    if pred:
        return {"predicted": True, "prediction": pred.to_dict()}
    return {"predicted": False, "prediction": None}


def cache_get_economics() -> dict[str, Any]:
    """Get statistical report of cache hits, tokens saved, latency saved, and cost reductions."""
    engine = get_global_cache_engine()
    econ = engine.get_economics()
    return {"success": True, **econ.to_dict()}


def cache_clear() -> dict[str, Any]:
    """Purge all entries from active semantic cache."""
    engine = get_global_cache_engine()
    count = engine.clear()
    return {"success": True, "cleared_entries_count": count}


def cache_warmup() -> dict[str, Any]:
    """Prime cache with standard default conversational queries."""
    engine = get_global_cache_engine()
    count = engine.warmup_defaults()
    return {"success": True, "warmed_up_count": count}


def get_cache_tools() -> list[Any]:
    """Return Cache tool functions for agent registration."""
    return [
        cache_lookup_query,
        cache_store_entry,
        cache_predict_tool,
        cache_get_economics,
        cache_clear,
        cache_warmup,
    ]
