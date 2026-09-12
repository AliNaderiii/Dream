"""Domain models and data structures for Semantic Caching & Token Economics."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CacheTier(str, Enum):
    """Hierarchy levels of caching."""

    L1_EXACT = "l1_exact"
    L2_SEMANTIC = "l2_semantic"
    L3_PERSISTENT = "l3_persistent"


@dataclass(slots=True)
class CacheEntry:
    """Cached response or tool execution result with token economics metadata."""

    id: str
    query: str
    response: str
    tier: CacheTier
    similarity_score: float = 1.0
    tokens_saved: int = 0
    latency_saved_ms: float = 0.0
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0  # 0.0 means no expiration
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: float | None = None) -> bool:
        """Check if cache entry has exceeded its TTL."""
        if self.expires_at <= 0.0:
            return False
        current_time = now if now is not None else time.time()
        return current_time > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Serialize cache entry to dictionary."""
        return {
            "id": self.id,
            "query": self.query,
            "response": self.response,
            "tier": self.tier.value,
            "similarity_score": round(self.similarity_score, 3),
            "tokens_saved": self.tokens_saved,
            "latency_saved_ms": round(self.latency_saved_ms, 2),
            "hit_count": self.hit_count,
            "created_at": round(self.created_at, 2),
            "expires_at": round(self.expires_at, 2),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class SpeculativePrediction:
    """Pre-computed or predicted tool result triggered by input pattern."""

    id: str
    trigger_pattern: str
    predicted_tool: str
    predicted_args: dict[str, Any]
    precomputed_result: Any
    confidence_score: float = 0.90
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize speculative prediction to dictionary."""
        return {
            "id": self.id,
            "trigger_pattern": self.trigger_pattern,
            "predicted_tool": self.predicted_tool,
            "predicted_args": self.predicted_args,
            "precomputed_result": self.precomputed_result,
            "confidence_score": round(self.confidence_score, 2),
            "hit_count": self.hit_count,
            "created_at": round(self.created_at, 2),
        }


@dataclass(slots=True)
class CacheEconomics:
    """Statistical summary of token savings, latency reductions, and financial economics."""

    total_requests: int
    l1_exact_hits: int
    l2_semantic_hits: int
    cache_misses: int
    total_tokens_saved: int
    total_latency_saved_ms: float
    estimated_cost_saved_usd: float
    active_entries_count: int

    @property
    def total_hits(self) -> int:
        return self.l1_exact_hits + self.l2_semantic_hits

    @property
    def hit_ratio(self) -> float:
        if self.total_requests <= 0:
            return 0.0
        return self.total_hits / self.total_requests

    def to_dict(self) -> dict[str, Any]:
        """Serialize cache economics to dictionary."""
        return {
            "total_requests": self.total_requests,
            "l1_exact_hits": self.l1_exact_hits,
            "l2_semantic_hits": self.l2_semantic_hits,
            "total_hits": self.total_hits,
            "cache_misses": self.cache_misses,
            "hit_ratio": round(self.hit_ratio, 3),
            "total_tokens_saved": self.total_tokens_saved,
            "total_latency_saved_ms": round(self.total_latency_saved_ms, 2),
            "estimated_cost_saved_usd": round(self.estimated_cost_saved_usd, 4),
            "active_entries_count": self.active_entries_count,
        }
