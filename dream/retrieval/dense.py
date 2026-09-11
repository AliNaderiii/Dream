"""Dense semantic vector store and cosine similarity retrieval engine."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dream.retrieval.sparse import tokenize_bilingual


def generate_pseudo_embedding(text: str, dim: int = 128) -> list[float]:
    """Generate a deterministic normalized n-gram pseudo-embedding in stdlib.

    Creates dense representations capturing semantic term overlap and character n-grams.
    """
    vec = [0.0] * dim
    tokens = tokenize_bilingual(text)
    if not tokens:
        return vec

    # Word-level features
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) % 2 == 0) else -1.0
        vec[idx] += sign * 1.0

        # Subword 3-grams
        for i in range(len(token) - 2):
            sub = token[i : i + 3]
            sub_h = int(hashlib.md5(sub.encode("utf-8")).hexdigest(), 16)
            sub_idx = sub_h % dim
            sub_sign = 1.0 if ((sub_h >> 8) % 2 == 0) else -1.0
            vec[sub_idx] += sub_sign * 0.4

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 1e-9:
        vec = [x / norm for x in vec]
    return vec


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two normalized float vectors."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=True))
    return max(-1.0, min(1.0, dot))


@dataclass
class DenseVectorStore:
    """In-memory dense vector store with cosine search and pluggable embedder."""

    embed_dim: int = 128
    embedder: Callable[[str], list[float]] | None = None
    vectors: dict[str, list[float]] = field(default_factory=dict)
    doc_contents: dict[str, str] = field(default_factory=dict)
    doc_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

    def embed(self, text: str) -> list[float]:
        """Convert text to embedding vector using active embedder."""
        if self.embedder is not None:
            try:
                res = self.embedder(text)
                if isinstance(res, list) and len(res) > 0:
                    return res
            except Exception:
                pass
        return generate_pseudo_embedding(text, self.embed_dim)

    def add_document(
        self,
        doc_id: str,
        text: str,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Embed and insert document into vector space."""
        vec = embedding if embedding is not None else self.embed(text)
        self.vectors[doc_id] = vec
        self.doc_contents[doc_id] = text
        self.doc_metadata[doc_id] = metadata or {}

    def remove_document(self, doc_id: str) -> None:
        """Remove document from vector space."""
        self.vectors.pop(doc_id, None)
        self.doc_contents.pop(doc_id, None)
        self.doc_metadata.pop(doc_id, None)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Search top-k most semantically similar documents by cosine distance."""
        if not self.vectors:
            return []

        q_vec = self.embed(query)
        scores: list[tuple[str, float]] = []

        for doc_id, doc_vec in self.vectors.items():
            sim = cosine_similarity(q_vec, doc_vec)
            # Rescale similarity from [-1, 1] to [0, 1]
            normalized_score = max(0.0, (sim + 1.0) / 2.0)
            scores.append((doc_id, normalized_score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
