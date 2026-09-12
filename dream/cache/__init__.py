"""Semantic Caching, Speculative Tool Execution, and Token Economics Subsystem."""

from __future__ import annotations

from dream.cache.engine import CacheEngine
from dream.cache.semantic import SemanticCache
from dream.cache.slash import handle_cache_slash_command
from dream.cache.speculative import SpeculativePrefetcher
from dream.cache.tools import (
    cache_clear,
    cache_get_economics,
    cache_lookup_query,
    cache_predict_tool,
    cache_store_entry,
    cache_warmup,
    get_cache_tools,
    get_global_cache_engine,
    reset_global_cache_engine,
)
from dream.cache.types import (
    CacheEconomics,
    CacheEntry,
    CacheTier,
    SpeculativePrediction,
)

# Register toolset if toolset registry is present
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="cache",
            description="Semantic caching, speculative pre-fetching, and token economics tools.",
            tools=[
                "cache_lookup_query",
                "cache_store_entry",
                "cache_predict_tool",
                "cache_get_economics",
                "cache_clear",
                "cache_warmup",
            ],
            metadata={"category": "cache", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "CacheEconomics",
    "CacheEngine",
    "CacheEntry",
    "CacheTier",
    "SemanticCache",
    "SpeculativePrediction",
    "SpeculativePrefetcher",
    "cache_clear",
    "cache_get_economics",
    "cache_lookup_query",
    "cache_predict_tool",
    "cache_store_entry",
    "cache_warmup",
    "get_cache_tools",
    "get_global_cache_engine",
    "handle_cache_slash_command",
    "reset_global_cache_engine",
]
