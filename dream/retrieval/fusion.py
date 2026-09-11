"""Hybrid rank fusion and temporal decay engine for multi-modal retrieval."""

from __future__ import annotations

import math
import time
from typing import Any

from dream.retrieval.types import (
    HybridSearchConfig,
    RetrievalResult,
    RetrievalScoreBreakdown,
)


def compute_temporal_decay(
    created_at: float,
    half_life_days: float = 30.0,
    current_time: float | None = None,
) -> float:
    """Calculate exponential temporal decay multiplier based on elapsed time."""
    if half_life_days <= 0:
        return 1.0
    now = current_time if current_time is not None else time.time()
    elapsed_seconds = max(0.0, now - created_at)
    elapsed_days = elapsed_seconds / 86400.0
    # Decay formula: exp(-ln(2) * elapsed / half_life)
    decay_lambda = math.log(2.0) / half_life_days
    return math.exp(-decay_lambda * elapsed_days)


class HybridFusionEngine:
    """Combines dense and sparse rankings with RRF and temporal multipliers."""

    def __init__(self, config: HybridSearchConfig | None = None) -> None:
        self.config = config or HybridSearchConfig()

    def fuse(
        self,
        sparse_hits: list[tuple[str, float]],
        dense_hits: list[tuple[str, float]],
        doc_store: dict[str, str],
        doc_metadata: dict[str, dict[str, Any]],
        top_k: int = 5,
        current_time: float | None = None,
        graph_boosts: dict[str, float] | None = None,
    ) -> list[RetrievalResult]:
        """Merge sparse and dense hits into unified ranked results."""
        boosts = graph_boosts or {}
        sparse_ranks = {doc_id: idx + 1 for idx, (doc_id, _) in enumerate(sparse_hits)}
        dense_ranks = {doc_id: idx + 1 for idx, (doc_id, _) in enumerate(dense_hits)}

        sparse_scores = dict(sparse_hits)
        dense_scores = dict(dense_hits)

        all_doc_ids = set(sparse_ranks.keys()) | set(dense_ranks.keys())
        results: list[RetrievalResult] = []

        # Min-max normalization for linear fusion if needed
        max_sparse = max(sparse_scores.values(), default=1.0) or 1.0
        max_dense = max(dense_scores.values(), default=1.0) or 1.0

        for doc_id in all_doc_ids:
            s_rank = sparse_ranks.get(doc_id, 0)
            d_rank = dense_ranks.get(doc_id, 0)
            s_score = sparse_scores.get(doc_id, 0.0)
            d_score = dense_scores.get(doc_id, 0.0)

            # RRF calculation: sum( weight / (k + rank) )
            rrf = 0.0
            if s_rank > 0:
                rrf += self.config.sparse_weight / (self.config.rrf_k + s_rank)
            if d_rank > 0:
                rrf += self.config.dense_weight / (self.config.rrf_k + d_rank)

            # Base score determination
            if self.config.fusion_mode == "linear":
                norm_s = s_score / max_sparse if max_sparse > 0 else 0.0
                norm_d = d_score / max_dense if max_dense > 0 else 0.0
                base_score = (norm_s * self.config.sparse_weight) + (
                    norm_d * self.config.dense_weight
                )
            else:
                base_score = rrf

            # Temporal decay calculation
            meta = doc_metadata.get(doc_id, {})
            created_at = meta.get("created_at", time.time())
            if self.config.enable_temporal_decay and not meta.get("pinned", False):
                temporal_mult = compute_temporal_decay(
                    created_at,
                    self.config.temporal_decay_half_life_days,
                    current_time,
                )
            else:
                temporal_mult = 1.0

            # Graph relevance boost
            g_boost = boosts.get(doc_id, 0.0)

            # Final composite score
            final_score = (base_score * temporal_mult) + g_boost

            if final_score < self.config.min_score_threshold:
                continue

            breakdown = RetrievalScoreBreakdown(
                sparse_bm25_score=s_score,
                sparse_bm25_rank=s_rank,
                dense_vector_score=d_score,
                dense_vector_rank=d_rank,
                rrf_score=rrf,
                temporal_multiplier=temporal_mult,
                graph_boost=g_boost,
                final_score=final_score,
            )

            res = RetrievalResult(
                doc_id=doc_id,
                content=doc_store.get(doc_id, ""),
                metadata=meta,
                score=final_score,
                breakdown=breakdown,
            )
            results.append(res)

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
