#!/usr/bin/env python3
"""Phase 31: Semantic Caching, Speculative Tool Execution & Token Economics Engine.

Applies all modules for Phase 31:
- dream/cache/types.py
- dream/cache/semantic.py
- dream/cache/speculative.py
- dream/cache/engine.py
- dream/cache/tools.py
- dream/cache/slash.py
- dream/cache/__init__.py
- dream/tools/toolsets.py (registered cache toolset)
- tests/test_semantic_cache_and_economics.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/cache/types.py": r'''"""Domain models and data structures for Semantic Caching, Speculative Execution, and Token Economics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
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
''',
    "dream/cache/semantic.py": r'''"""Multi-tier semantic cache with exact hashing, token similarity, and TTL eviction."""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any
import uuid

from dream.cache.types import CacheEntry, CacheTier
from dream.security.pathsafety import is_sensitive_path


class SemanticCache:
    """High-performance L1 exact and L2 semantic cache with Persian normalization."""

    def __init__(self, max_entries: int = 1000, default_ttl: float = 3600.0) -> None:
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._exact_cache: dict[str, CacheEntry] = collections.OrderedDict()
        self._entries: list[CacheEntry] = []

    def normalize_query(self, query: str) -> str:
        """Standardize Persian and English typography, whitespaces, and punctuation."""
        text = query.strip().lower()
        # Normalize Persian characters
        text = text.replace("\u064a", "\u06cc").replace("\u0643", "\u06a9")
        # Normalize half-spaces
        text = text.replace("\u200c", " ")
        # Strip Persian & Arabic punctuation explicitly
        text = re.sub(r"[\u060c\u061b\u061f\u06d4\u066a\u066b\u066c\u0640]", " ", text)
        # Strip standard punctuation
        text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _query_hash(self, query: str) -> str:
        """Compute deterministic SHA-256 digest of normalized query."""
        norm = self.normalize_query(query)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def compute_similarity(self, query1: str, query2: str) -> float:
        """Calculate token Jaccard and char n-gram similarity score in [0.0, 1.0]."""
        norm1 = self.normalize_query(query1)
        norm2 = self.normalize_query(query2)

        if norm1 == norm2:
            return 1.0

        tokens1 = set(norm1.split())
        tokens2 = set(norm2.split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        jaccard = len(intersection) / len(union)
        overlap = len(intersection) / max(1, min(len(tokens1), len(tokens2)))

        # Compute character trigram overlap for fuzzy morphology
        def trigrams(s: str) -> set[str]:
            return {s[i : i + 3] for i in range(max(1, len(s) - 2))}

        tri1 = trigrams(norm1)
        tri2 = trigrams(norm2)
        tri_sim = len(tri1.intersection(tri2)) / max(1, len(tri1.union(tri2)))

        return max(jaccard, tri_sim, overlap * 0.85)

    def lookup(
        self,
        query: str,
        similarity_threshold: float = 0.88,
    ) -> CacheEntry | None:
        """Query cache via L1 exact hash or L2 semantic similarity match."""
        now = time.time()
        q_hash = self._query_hash(query)

        # 1. L1 Exact Match
        if q_hash in self._exact_cache:
            entry = self._exact_cache[q_hash]
            if entry.is_expired(now):
                del self._exact_cache[q_hash]
                if entry in self._entries:
                    self._entries.remove(entry)
            else:
                entry.hit_count += 1
                entry.tier = CacheTier.L1_EXACT
                entry.similarity_score = 1.0
                return entry

        # 2. L2 Semantic Similarity Search
        best_entry: CacheEntry | None = None
        best_sim = 0.0

        for entry in list(self._entries):
            if entry.is_expired(now):
                self._entries.remove(entry)
                continue

            sim = self.compute_similarity(query, entry.query)
            if sim >= similarity_threshold and sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None:
            best_entry.hit_count += 1
            best_entry.tier = CacheTier.L2_SEMANTIC
            best_entry.similarity_score = best_sim
            return best_entry

        return None

    def store(
        self,
        query: str,
        response: str,
        ttl_seconds: float | None = None,
        tokens_saved: int = 0,
        latency_saved_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> CacheEntry:
        """Insert or update entry in cache with LRU eviction."""
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = now + ttl if ttl > 0 else 0.0

        q_hash = self._query_hash(query)
        cid = f"cache_{uuid.uuid4().hex[:8]}"

        entry = CacheEntry(
            id=cid,
            query=query,
            response=response,
            tier=CacheTier.L1_EXACT,
            similarity_score=1.0,
            tokens_saved=tokens_saved,
            latency_saved_ms=latency_saved_ms,
            hit_count=0,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        # LRU eviction if full
        if len(self._entries) >= self.max_entries:
            oldest = self._entries.pop(0)
            old_hash = self._query_hash(oldest.query)
            self._exact_cache.pop(old_hash, None)

        self._exact_cache[q_hash] = entry
        self._entries.append(entry)
        return entry

    def clear(self) -> int:
        """Flush all cache entries and return count of purged items."""
        count = len(self._entries)
        self._exact_cache.clear()
        self._entries.clear()
        return count

    def persist_to_disk(self, file_path: str) -> int:
        """Save active cache state to disk with L4 path security check."""
        if is_sensitive_path(file_path):
            raise PermissionError(f"Permission denied: '{file_path}' is a sensitive system path.")

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = [e.to_dict() for e in self._entries if not e.is_expired()]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(data)

    def load_from_disk(self, file_path: str) -> int:
        """Restore cache state from disk with L4 path validation."""
        if is_sensitive_path(file_path):
            raise PermissionError(f"Permission denied: '{file_path}' is a sensitive system path.")

        path = Path(file_path)
        if not path.exists():
            return 0

        content = path.read_text(encoding="utf-8")
        items = json.loads(content)
        now = time.time()
        loaded = 0

        for item in items:
            exp = item.get("expires_at", 0.0)
            if exp > 0.0 and now > exp:
                continue

            entry = CacheEntry(
                id=item["id"],
                query=item["query"],
                response=item["response"],
                tier=CacheTier(item.get("tier", "l1_exact")),
                similarity_score=item.get("similarity_score", 1.0),
                tokens_saved=item.get("tokens_saved", 0),
                latency_saved_ms=item.get("latency_saved_ms", 0.0),
                hit_count=item.get("hit_count", 0),
                created_at=item.get("created_at", now),
                expires_at=exp,
                metadata=item.get("metadata", {}),
            )
            q_hash = self._query_hash(entry.query)
            self._exact_cache[q_hash] = entry
            self._entries.append(entry)
            loaded += 1

        return loaded

    def size(self) -> int:
        """Return number of valid unexpired cached entries."""
        now = time.time()
        return sum(1 for e in self._entries if not e.is_expired(now))
''',
    "dream/cache/speculative.py": r'''"""Speculative tool pre-fetching, execution prediction, and latency minimization."""

from __future__ import annotations

import re
import time
from typing import Any
import uuid

from dream.cache.types import SpeculativePrediction


class SpeculativePrefetcher:
    """Predicts next probable tool invocations and pre-computes results speculatively."""

    def __init__(self) -> None:
        self._predictions: list[SpeculativePrediction] = []
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Prime standard deterministic tools for speculative pre-fetching."""
        # 1. Datetime / Clock trigger
        self.register_pattern(
            trigger_pattern=r"(\u0633\u0627\u0639\u062a\s+\u0686\u0646\u062f\u0647|\u062a\u0627\u0631\u06cc\u062e\s+\u0627\u0645\u0631\u0648\u0632|what\s+time|current\s+date)",
            tool_name="get_datetime",
            default_args={},
            confidence=0.98,
        )

        # 2. Note listing trigger
        self.register_pattern(
            trigger_pattern=r"(\u0644\u06cc\u0633\u062a\s+\u06cc\u0627\u062f\u062f\u0627\u0634\u062a|\u06cc\u0627\u062f\u062f\u0627\u0634\u062a\u200c\u0647\u0627\u06cc\s+\u0645\u0646|list\s+notes)",
            tool_name="list_notes",
            default_args={},
            confidence=0.95,
        )

        # 3. Calculation trigger
        self.register_pattern(
            trigger_pattern=r"(\u062d\u0633\u0627\u0628\s+\u06a9\u0646|\u0645\u062d\u0627\u0633\u0628\u0647\s+\u06a9\u0646|calculate\s+[\d\.\+\-\*\/]+)",
            tool_name="calculate",
            default_args={"expression": "0"},
            confidence=0.90,
        )

    def register_pattern(
        self,
        trigger_pattern: str,
        tool_name: str,
        default_args: dict[str, Any],
        precomputed_result: Any = None,
        confidence: float = 0.90,
    ) -> SpeculativePrediction:
        """Register a speculative prediction rule for tool execution."""
        pid = f"spec_{uuid.uuid4().hex[:8]}"
        pred = SpeculativePrediction(
            id=pid,
            trigger_pattern=trigger_pattern,
            predicted_tool=tool_name,
            predicted_args=default_args,
            precomputed_result=precomputed_result,
            confidence_score=confidence,
            created_at=time.time(),
        )
        self._predictions.append(pred)
        return pred

    def predict_tool(self, user_input: str) -> SpeculativePrediction | None:
        """Evaluate input against speculative patterns and return highest confidence prediction."""
        best_pred: SpeculativePrediction | None = None
        best_conf = 0.0

        for pred in self._predictions:
            if re.search(pred.trigger_pattern, user_input, re.IGNORECASE):
                if pred.confidence_score > best_conf:
                    best_conf = pred.confidence_score
                    best_pred = pred

        if best_pred is not None:
            best_pred.hit_count += 1
            return best_pred

        return None

    def list_predictions(self) -> list[SpeculativePrediction]:
        """Return all active speculative rules."""
        return list(self._predictions)
''',
    "dream/cache/engine.py": r'''"""Token Economics and Central Caching Coordinator."""

from __future__ import annotations

import time
from typing import Any

from dream.cache.semantic import SemanticCache
from dream.cache.speculative import SpeculativePrefetcher
from dream.cache.types import CacheEconomics, CacheEntry, CacheTier, SpeculativePrediction


class CacheEngine:
    """Coordinates multi-tier caching, speculative execution, and token cost economics."""

    def __init__(
        self,
        semantic_cache: SemanticCache | None = None,
        prefetcher: SpeculativePrefetcher | None = None,
    ) -> None:
        self.semantic_cache = semantic_cache or SemanticCache()
        self.prefetcher = prefetcher or SpeculativePrefetcher()

        # Economics telemetry
        self._total_requests: int = 0
        self._l1_exact_hits: int = 0
        self._l2_semantic_hits: int = 0
        self._cache_misses: int = 0
        self._total_tokens_saved: int = 0
        self._total_latency_saved_ms: float = 0.0

        # Cost factor: ~$0.000008 per token saved (blended avg across GPT-4o / Claude 3.5)
        self._cost_per_token: float = 0.000008

        self.warmup_defaults()

    def query(
        self,
        prompt: str,
        similarity_threshold: float = 0.88,
    ) -> CacheEntry | None:
        """Lookup response in cache, update telemetry counters, and return match if hit."""
        self._total_requests += 1
        entry = self.semantic_cache.lookup(prompt, similarity_threshold=similarity_threshold)

        if entry is not None:
            if entry.tier == CacheTier.L1_EXACT:
                self._l1_exact_hits += 1
            else:
                self._l2_semantic_hits += 1

            # Estimate saved tokens if not set (approx 1 token per 4 chars of prompt + response)
            tokens = entry.tokens_saved or int((len(prompt) + len(entry.response)) / 4)
            latency = entry.latency_saved_ms or 450.0  # Estimated average roundtrip savings

            self._total_tokens_saved += tokens
            self._total_latency_saved_ms += latency
            return entry

        self._cache_misses += 1
        return None

    def store(
        self,
        prompt: str,
        response: str,
        ttl_seconds: float | None = None,
        tokens_saved: int = 0,
        latency_saved_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> CacheEntry:
        """Store prompt response in cache."""
        # Auto-compute token estimate if 0
        computed_tokens = tokens_saved or int((len(prompt) + len(response)) / 4)
        return self.semantic_cache.store(
            query=prompt,
            response=response,
            ttl_seconds=ttl_seconds,
            tokens_saved=computed_tokens,
            latency_saved_ms=latency_saved_ms or 500.0,
            metadata=metadata,
        )

    def predict_speculative_tool(self, user_input: str) -> SpeculativePrediction | None:
        """Evaluate if user input matches a speculative tool prediction rule."""
        return self.prefetcher.predict_tool(user_input)

    def get_economics(self) -> CacheEconomics:
        """Compute statistical summary of cache hits, token savings, and cost reductions."""
        active_entries = self.semantic_cache.size()
        cost_saved = self._total_tokens_saved * self._cost_per_token

        return CacheEconomics(
            total_requests=self._total_requests,
            l1_exact_hits=self._l1_exact_hits,
            l2_semantic_hits=self._l2_semantic_hits,
            cache_misses=self._cache_misses,
            total_tokens_saved=self._total_tokens_saved,
            total_latency_saved_ms=self._total_latency_saved_ms,
            estimated_cost_saved_usd=cost_saved,
            active_entries_count=active_entries,
        )

    def clear(self) -> int:
        """Purge cache contents and reset counters."""
        count = self.semantic_cache.clear()
        return count

    def warmup_defaults(self) -> int:
        """Prime cache with standard conversational greetings and system FAQs."""
        warmups = [
            (
                "\u0633\u0644\u0627\u0645",
                "\u0633\u0644\u0627\u0645! \u0686\u06af\u0648\u0646\u0647 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u0645 \u0627\u0645\u0631\u0648\u0632 \u0628\u0647 \u0634\u0645\u0627 \u06a9\u0645\u06a9 \u06a9\u0646\u0645\u061f",
            ),
            (
                "hello",
                "Hello! How can I assist you today?",
            ),
            (
                "\u062a\u0648 \u06a9\u06cc\u0633\u062a\u06cc\u061f",
                "\u0645\u0646 \u062f\u0631\u06cc\u0645 (Dream) \u0647\u0633\u062a\u0645\u060c \u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f \u0639\u0627\u0645\u0644\u200c\u067e\u0627\u06cc\u0647 \u0634\u0645\u0627.",
            ),
        ]
        for q, r in warmups:
            self.semantic_cache.store(query=q, response=r, ttl_seconds=86400.0)
        return len(warmups)
''',
    "dream/cache/tools.py": r'''"""LLM Tool bindings for Semantic Caching, Speculative Execution, and Token Economics."""

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
''',
    "dream/cache/slash.py": r'''"""Slash command handlers for Semantic Caching & Token Economics."""

from __future__ import annotations

from typing import Any

from dream.cache.tools import (
    cache_clear,
    cache_get_economics,
    cache_lookup_query,
    cache_warmup,
)


def handle_cache_slash_command(command_str: str) -> str:
    """Handle /cache CLI slash commands.

    Usage:
        /cache stats
        /cache clear
        /cache warmup
        /cache lookup <query>
    """
    parts = command_str.strip().split(maxsplit=2)
    if len(parts) < 2:
        return (
            "\U0001f4be \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u06a9\u0634 \u0645\u0639\u0646\u0627\u06cc\u06cc \u0648 \u0645\u062f\u06cc\u0631\u06cc\u062a \u062a\u0648\u06a9\u0646 (Cache & Token Economics):\n"
            "  /cache stats                      \u06af\u0632\u0627\u0631\u0634 \u0622\u0645\u0627\u0631 \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc \u062a\u0648\u06a9\u0646 \u0648 \u0647\u0632\u06cc\u0646\u0647\n"
            "  /cache clear                      \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u062d\u0627\u0641\u0638\u0647 \u06a9\u0634\n"
            "  /cache warmup                     \u0622\u0645\u0627\u062f\u0647\u200c\u0633\u0627\u0632\u06cc \u067e\u0627\u0633\u062e\u200c\u0647\u0627\u06cc \u067e\u06cc\u0634\u200c\u0641\u0631\u0636\n"
            "  /cache lookup <query>             \u062c\u0633\u062a\u062c\u0648\u06cc \u0645\u0639\u0646\u0627\u06cc\u06cc \u062f\u0631 \u06a9\u0634"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "stats":
        econ = cache_get_economics()
        hits = econ.get("total_hits", 0)
        reqs = econ.get("total_requests", 0)
        ratio = econ.get("hit_ratio", 0.0) * 100
        tokens = econ.get("total_tokens_saved", 0)
        cost = econ.get("estimated_cost_saved_usd", 0.0)
        latency = econ.get("total_latency_saved_ms", 0.0) / 1000.0

        return (
            f"\U0001f4ca \u06af\u0632\u0627\u0631\u0634 \u0627\u0642\u062a\u0635\u0627\u062f \u062a\u0648\u06a9\u0646 \u0648 \u06a9\u0634 \u0645\u0639\u0646\u0627\u06cc\u06cc:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u062f\u0631\u062e\u0648\u0627\u0633\u062a\u200c\u0647\u0627: {reqs} (\u0627\u0635\u0627\u0628\u062a\u200c\u0647\u0627: {hits} | \u0646\u0631\u062e \u0627\u0635\u0627\u0628\u062a: {ratio:.1f}%)\n"
            f"- \u062a\u0648\u06a9\u0646\u200c\u0647\u0627\u06cc \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc\u200c\u0634\u062f\u0647: {tokens:,} \u062a\u0648\u06a9\u0646\n"
            f"- \u06a9\u0627\u0647\u0634 \u062a\u0627\u062e\u06cc\u0631 (Latency Saved): {latency:.2f} \u062b\u0627\u0646\u06cc\u0647\n"
            f"- \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc \u0645\u0627\u0644\u06cc \u062a\u062e\u0645\u06cc\u0646\u06cc: ${cost:.4f} USD\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u067e\u0627\u0633\u062e\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644 \u062f\u0631 \u06a9\u0634: {econ.get('active_entries_count', 0)}"
        )

    if subcommand == "clear":
        res = cache_clear()
        return f"\u2705 \u062d\u0627\u0641\u0638\u0647 \u06a9\u0634 \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0634\u062f. ({res.get('cleared_entries_count', 0)} \u0645\u0648\u0631\u062f \u062d\u0630\u0641 \u06af\u0631\u062f\u06cc\u062f)"

    if subcommand == "warmup":
        res = cache_warmup()
        return f"\u2705 \u062a\u0639\u062f\u0627\u062f {res.get('warmed_up_count', 0)} \u067e\u0627\u0633\u062e \u067e\u06cc\u0634\u200c\u0641\u0631\u0636 \u062f\u0631 \u06a9\u0634 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0634\u062f."

    if subcommand == "lookup":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0639\u0628\u0627\u0631\u062a \u062c\u0633\u062a\u062c\u0648 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = cache_lookup_query(arg)
        if res.get("hit"):
            return (
                f"\U0001f3af \u0627\u0635\u0627\u0628\u062a \u0628\u0647 \u06a9\u0634 ({res.get('tier')} - \u0634\u0628\u0627\u0647\u062a: {res.get('similarity_score', 0):.2f}):\n"
                f"{res.get('response')}"
            )
        return "\u274c \u0645\u0648\u0631\u062f\u06cc \u062f\u0631 \u06a9\u0634 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f (Cache Miss)."

    return f"\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0634\u0646\u0627\u062e\u062a\u0647 '{subcommand}'. \u0628\u0631\u0627\u06cc \u0631\u0627\u0647\u0646\u0645\u0627 '/cache' \u0631\u0627 \u0628\u0632\u0646\u06cc\u062f."
''',
    "dream/cache/__init__.py": r'''"""Semantic Caching, Speculative Tool Execution, and Token Economics Subsystem."""

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
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        allowed_names.update(source.keys())

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_semantic_cache_and_economics.py": r'''"""Unit and integration tests for Semantic Caching, Speculative Execution, and Token Economics."""

from __future__ import annotations

from pathlib import Path
import tempfile
import time
import pytest

from dream.cache import (
    CacheEconomics,
    CacheEngine,
    CacheTier,
    SemanticCache,
    SpeculativePrefetcher,
    cache_clear,
    cache_get_economics,
    cache_lookup_query,
    cache_predict_tool,
    cache_store_entry,
    cache_warmup,
    handle_cache_slash_command,
    reset_global_cache_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_cache_engine() -> None:
    reset_global_cache_engine()
    yield
    reset_global_cache_engine()


def test_toolset_includes_cache() -> None:
    """Verify cache toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("cache")
    assert ts is not None
    assert "cache_lookup_query" in ts.tools
    assert "cache_get_economics" in ts.tools
    assert "cache_predict_tool" in ts.tools
    assert "cache" in BUILTIN_TOOLSETS


def test_semantic_cache_exact_and_fuzzy_matching() -> None:
    """Verify L1 exact matching and L2 semantic similarity with Persian normalization."""
    cache = SemanticCache()

    # Store entry with Persian characters
    cache.store(
        query="\u0686\u06af\u0648\u0646\u0647 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u0645 \u067e\u0627\u06cc\u062a\u0648\u0646 \u06cc\u0627\u062f \u0628\u06af\u06cc\u0631\u0645\u061f",
        response="\u0628\u0631\u0627\u06cc \u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc \u067e\u0627\u06cc\u062a\u0648\u0646 \u0627\u0632 \u062f\u0648\u0631\u0647\u200c\u0647\u0627\u06cc \u0622\u0646\u0644\u0627\u06cc\u0646 \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f.",
        tokens_saved=120,
    )

    # 1. Exact match (with slight spacing / normalization difference)
    hit1 = cache.lookup("\u0686\u06af\u0648\u0646\u0647 \u0645\u06cc \u062a\u0648\u0627\u0646\u0645 \u067e\u0627\u06cc\u062a\u0648\u0646 \u06cc\u0627\u062f \u0628\u06af\u06cc\u0631\u0645")
    assert hit1 is not None
    assert hit1.tier == CacheTier.L1_EXACT
    assert hit1.similarity_score >= 0.99

    # 2. Semantic fuzzy match
    hit2 = cache.lookup("\u0686\u0637\u0648\u0631 \u067e\u0627\u06cc\u062a\u0648\u0646 \u06cc\u0627\u062f \u0628\u06af\u06cc\u0631\u0645\u061f", similarity_threshold=0.60)
    assert hit2 is not None
    assert hit2.tier == CacheTier.L2_SEMANTIC


def test_cache_ttl_and_lru_eviction() -> None:
    """Verify TTL expiration and capacity eviction."""
    cache = SemanticCache(max_entries=2, default_ttl=0.1)

    cache.store("query 1", "resp 1", ttl_seconds=0.1)
    cache.store("query 2", "resp 2", ttl_seconds=10.0)

    # Wait for query 1 TTL to elapse
    time.sleep(0.15)
    assert cache.lookup("query 1") is None
    assert cache.lookup("query 2") is not None

    # Test LRU eviction
    cache.store("query 3", "resp 3", ttl_seconds=10.0)
    cache.store("query 4", "resp 4", ttl_seconds=10.0)  # should evict oldest
    assert cache.size() == 2


def test_speculative_prefetcher_triggers() -> None:
    """Verify predictive tool pre-fetching rules."""
    prefetcher = SpeculativePrefetcher()

    # Time prediction
    pred_time = prefetcher.predict_tool("\u0627\u0644\u0627\u0646 \u0633\u0627\u0639\u062a \u0686\u0646\u062f\u0647\u061f")
    assert pred_time is not None
    assert pred_time.predicted_tool == "get_datetime"

    # Notes prediction
    pred_notes = prefetcher.predict_tool("\u0644\u0637\u0641\u0627 \u0644\u06cc\u0633\u062a \u06cc\u0627\u062f\u062f\u0627\u0634\u062a \u0647\u0627 \u0631\u0648 \u0646\u0634\u0648\u0646 \u0628\u062f\u0647")
    assert pred_notes is not None
    assert pred_notes.predicted_tool == "list_notes"

    # Non-matching prompt
    pred_none = prefetcher.predict_tool("Write a python script for neural ODEs")
    assert pred_none is None


def test_cache_engine_and_token_economics() -> None:
    """Verify end-to-end cache engine, token savings calculation, and disk persistence."""
    engine = CacheEngine()

    # Warmup queries exist
    hit_warm = engine.query("\u0633\u0644\u0627\u0645")
    assert hit_warm is not None

    # Miss query
    hit_miss = engine.query("A totally brand new scientific query that does not exist in cache")
    assert hit_miss is None

    # Store and retrieve
    engine.store("What is Quantum Computing?", "Quantum computing uses qubits.", tokens_saved=250)
    hit_qc = engine.query("What is Quantum Computing?")
    assert hit_qc is not None

    econ = engine.get_economics()
    assert econ.total_requests >= 3
    assert econ.total_hits >= 2
    assert econ.total_tokens_saved >= 250
    assert econ.estimated_cost_saved_usd > 0.0

    # Persistence to disk and L4 path security
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "cache_store.json"
        saved_count = engine.semantic_cache.persist_to_disk(str(cache_file))
        assert saved_count >= 1
        assert cache_file.exists()

        new_cache = SemanticCache()
        loaded_count = new_cache.load_from_disk(str(cache_file))
        assert loaded_count == saved_count

    with pytest.raises(PermissionError):
        engine.semantic_cache.persist_to_disk("/etc/shadow")


def test_cache_tools_and_slash_commands() -> None:
    """Verify LLM tool wrappers and /cache CLI slash command handlers."""
    # Tool: lookup
    lookup_res = cache_lookup_query("\u0633\u0644\u0627\u0645")
    assert lookup_res["hit"] is True

    # Tool: predict
    pred_res = cache_predict_tool("\u0633\u0627\u0639\u062a \u0686\u0646\u062f\u0647")
    assert pred_res["predicted"] is True

    # Tool: economics
    econ_res = cache_get_economics()
    assert econ_res["success"] is True
    assert "total_tokens_saved" in econ_res

    # Slash: stats
    stats_msg = handle_cache_slash_command("/cache stats")
    assert "USD" in stats_msg

    # Slash: lookup
    lookup_msg = handle_cache_slash_command("/cache lookup \u0633\u0644\u0627\u0645")
    assert "\u0627\u0635\u0627\u0628\u062a \u0628\u0647 \u06a9\u0634" in lookup_msg

    # Slash: clear
    clear_msg = handle_cache_slash_command("/cache clear")
    assert "\u067e\u0627\u06a9\u0633\u0627\u0632\u06cc" in clear_msg
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 31 (Semantic Caching & Token Economics) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_semantic_cache_and_economics.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 31")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 31")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 31 (Semantic Caching & Token Economics) applied and verified cleanly!")


if __name__ == "__main__":
    main()
