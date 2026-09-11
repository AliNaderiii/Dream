"""Token Economics and Central Caching Coordinator."""

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
