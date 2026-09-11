#!/usr/bin/env python3
"""apply_pr18.py - Standalone installer for Phase 15 / PR #18:
Hybrid Semantic Retrieval & Knowledge Graph Memory Subsystem.

This installer creates or updates the following files in the target repository:
  - dream/retrieval/__init__.py
  - dream/retrieval/types.py
  - dream/retrieval/sparse.py
  - dream/retrieval/dense.py
  - dream/retrieval/fusion.py
  - dream/retrieval/graph.py
  - dream/retrieval/engine.py
  - dream/retrieval/tools.py
  - dream/retrieval/slash.py
  - dream/tools/toolsets.py
  - tests/test_retrieval_and_knowledge_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RETRIEVAL_TYPES = '''"""Data types and domain models for hybrid semantic retrieval and knowledge graph memory."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Entity:
    """A semantic entity in the knowledge graph (e.g. Person, Project, Concept)."""

    id: str
    name: str
    entity_type: str = "concept"  # person, project, tool, preference, concept, organization
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    user_id: str = "default"

    def matches(self, term: str) -> bool:
        """Check if term matches entity name or any alias case-insensitively."""
        t = term.strip().lower()
        if self.name.lower() == t:
            return True
        return any(a.lower() == t for a in self.aliases)


@dataclass(slots=True)
class Relation:
    """A directed semantic edge connecting two entities in the knowledge graph."""

    id: str
    source_id: str
    target_id: str
    relation_type: str  # uses, builds, prefers, belongs_to, works_at, relates_to, depends_on
    weight: float = 1.0
    context: str = ""
    created_at: float = field(default_factory=time.time)
    user_id: str = "default"


@dataclass(slots=True)
class RetrievalScoreBreakdown:
    """Detailed score decomposition for a hybrid search result."""

    sparse_bm25_score: float = 0.0
    sparse_bm25_rank: int = 0
    dense_vector_score: float = 0.0
    dense_vector_rank: int = 0
    rrf_score: float = 0.0
    temporal_multiplier: float = 1.0
    graph_boost: float = 0.0
    final_score: float = 0.0


@dataclass(slots=True)
class RetrievalResult:
    """Ranked search result item returned by the hybrid engine."""

    doc_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    breakdown: RetrievalScoreBreakdown = field(default_factory=RetrievalScoreBreakdown)
    related_entities: list[str] = field(default_factory=list)
    graph_context: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HybridSearchConfig:
    """Configuration tunables for hybrid semantic retrieval and fusion."""

    dense_weight: float = 0.5
    sparse_weight: float = 0.5
    rrf_k: int = 60
    fusion_mode: str = "rrf"  # "rrf" or "linear"
    temporal_decay_half_life_days: float = 30.0
    enable_temporal_decay: bool = True
    graph_hop_limit: int = 2
    min_score_threshold: float = 0.01
'''

RETRIEVAL_SPARSE = '''"""BM25 sparse retrieval engine supporting bilingual Persian and English indexing."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from dream.memory.normalization import normalize_fa


def tokenize_bilingual(text: str) -> list[str]:
    """Tokenize and normalize Persian and English text into clean terms."""
    norm = normalize_fa(text)
    # Extract Persian and Latin alphanumeric words
    tokens = re.findall(r"[\\w]+", norm.lower(), flags=re.UNICODE)
    # Filter single-letter non-alphanumeric noise
    return [t for t in tokens if len(t) > 1 or t.isdigit()]


@dataclass
class BM25Engine:
    """Inverted index BM25 sparse scoring engine."""

    k1: float = 1.5
    b: float = 0.75
    doc_count: int = 0
    avg_doc_len: float = 0.0
    doc_lengths: dict[str, int] = field(default_factory=dict)
    doc_contents: dict[str, str] = field(default_factory=dict)
    doc_metadata: dict[str, dict] = field(default_factory=dict)
    inverted_index: dict[str, dict[str, int]] = field(default_factory=dict)
    doc_freqs: dict[str, int] = field(default_factory=dict)

    def add_document(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """Add or update a document in the BM25 index."""
        if doc_id in self.doc_contents:
            self.remove_document(doc_id)

        tokens = tokenize_bilingual(text)
        length = len(tokens)
        self.doc_lengths[doc_id] = length
        self.doc_contents[doc_id] = text
        self.doc_metadata[doc_id] = metadata or {}

        term_counts = Counter(tokens)
        for term, count in term_counts.items():
            if term not in self.inverted_index:
                self.inverted_index[term] = {}
                self.doc_freqs[term] = 0
            self.inverted_index[term][doc_id] = count
            self.doc_freqs[term] += 1

        self.doc_count = len(self.doc_lengths)
        self.avg_doc_len = sum(self.doc_lengths.values()) / max(1, self.doc_count)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the BM25 index."""
        if doc_id not in self.doc_contents:
            return
        tokens = tokenize_bilingual(self.doc_contents[doc_id])
        distinct_terms = set(tokens)
        for term in distinct_terms:
            if term in self.inverted_index and doc_id in self.inverted_index[term]:
                del self.inverted_index[term][doc_id]
                self.doc_freqs[term] = max(0, self.doc_freqs[term] - 1)
                if not self.inverted_index[term]:
                    del self.inverted_index[term]
                    del self.doc_freqs[term]

        del self.doc_contents[doc_id]
        del self.doc_lengths[doc_id]
        if doc_id in self.doc_metadata:
            del self.doc_metadata[doc_id]

        self.doc_count = len(self.doc_lengths)
        self.avg_doc_len = (
            sum(self.doc_lengths.values()) / max(1, self.doc_count) if self.doc_count > 0 else 0.0
        )

    def compute_idf(self, term: str) -> float:
        """Compute Robertson-Spärck Jones IDF with smoothing."""
        df = self.doc_freqs.get(term, 0)
        if df == 0:
            return 0.0
        n = self.doc_count
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Compute BM25 score for query against all documents."""
        if self.doc_count == 0:
            return []

        query_tokens = tokenize_bilingual(query)
        if not query_tokens:
            return []

        scores: dict[str, float] = {}
        for term in set(query_tokens):
            if term not in self.inverted_index:
                continue
            idf = self.compute_idf(term)
            for doc_id, tf in self.inverted_index[term].items():
                doc_len = self.doc_lengths.get(doc_id, self.avg_doc_len)
                len_norm = 1.0 - self.b + self.b * (doc_len / max(1.0, self.avg_doc_len))
                denom = tf + self.k1 * len_norm
                term_score = idf * (tf * (self.k1 + 1.0)) / max(1e-6, denom)
                scores[doc_id] = scores.get(doc_id, 0.0) + term_score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
'''

RETRIEVAL_DENSE = '''"""Dense semantic vector store and cosine similarity retrieval engine."""

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
'''

RETRIEVAL_FUSION = '''"""Hybrid rank fusion and temporal decay engine for multi-modal retrieval."""

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
'''

RETRIEVAL_GRAPH = '''"""Knowledge Graph Memory: Entity-Relation-Entity graph with multi-hop retrieval."""

from __future__ import annotations

import collections
import json
import re
import sqlite3
import time
import uuid
from typing import Any

from dream.retrieval.types import Entity, Relation


class KnowledgeGraphStore:
    """Relational and in-memory knowledge graph for semantic associative linking."""

    def __init__(self, db_path: str | None = None, user_id: str = "default") -> None:
        self.user_id = user_id
        self._db_path = db_path or ":memory:"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        """Initialize relational entity-relation schema."""
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kg_entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    aliases_json TEXT DEFAULT '[]',
                    attributes_json TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    user_id TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kg_relations (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    context TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    user_id TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES kg_entities (id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES kg_entities (id) ON DELETE CASCADE
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_entities_name ON kg_entities (name, user_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_src ON kg_relations "
                "(source_id, user_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_tgt ON kg_relations "
                "(target_id, user_id)"
            )

    def add_entity(
        self,
        name: str,
        entity_type: str = "concept",
        description: str = "",
        aliases: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        entity_id: str | None = None,
    ) -> Entity:
        """Insert or update an entity node in the graph."""
        clean_name = name.strip()
        existing = self.find_entity(clean_name)
        now = time.time()
        aliases_list = aliases or []
        attrs = attributes or {}

        if existing:
            # Update existing entity
            merged_aliases = list(set(existing.aliases + aliases_list))
            merged_attrs = {**existing.attributes, **attrs}
            desc = description if description else existing.description
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE kg_entities
                    SET entity_type = ?, description = ?, aliases_json = ?, attributes_json = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        entity_type or existing.entity_type,
                        desc,
                        json.dumps(merged_aliases, ensure_ascii=False),
                        json.dumps(merged_attrs, ensure_ascii=False),
                        existing.id,
                        self.user_id,
                    ),
                )
            return Entity(
                id=existing.id,
                name=existing.name,
                entity_type=entity_type or existing.entity_type,
                description=desc,
                aliases=merged_aliases,
                attributes=merged_attrs,
                created_at=existing.created_at,
                user_id=self.user_id,
            )

        new_id = entity_id or f"ent_{uuid.uuid4().hex[:10]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO kg_entities (
                    id, name, entity_type, description, aliases_json,
                    attributes_json, created_at, user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    clean_name,
                    entity_type,
                    description,
                    json.dumps(aliases_list, ensure_ascii=False),
                    json.dumps(attrs, ensure_ascii=False),
                    now,
                    self.user_id,
                ),
            )
        return Entity(
            id=new_id,
            name=clean_name,
            entity_type=entity_type,
            description=description,
            aliases=aliases_list,
            attributes=attrs,
            created_at=now,
            user_id=self.user_id,
        )

    def find_entity(self, name_or_alias: str) -> Entity | None:
        """Find entity by exact name or match in aliases."""
        term = name_or_alias.strip().lower()
        rows = self._conn.execute(
            "SELECT * FROM kg_entities WHERE user_id = ?",
            (self.user_id,),
        ).fetchall()
        for row in rows:
            aliases = json.loads(row["aliases_json"] or "[]")
            if row["name"].lower() == term or any(a.lower() == term for a in aliases):
                return Entity(
                    id=row["id"],
                    name=row["name"],
                    entity_type=row["entity_type"],
                    description=row["description"],
                    aliases=aliases,
                    attributes=json.loads(row["attributes_json"] or "{}"),
                    created_at=row["created_at"],
                    user_id=row["user_id"],
                )
        return None

    def get_entity_by_id(self, entity_id: str) -> Entity | None:
        """Fetch entity by unique ID."""
        row = self._conn.execute(
            "SELECT * FROM kg_entities WHERE id = ? AND user_id = ?",
            (entity_id, self.user_id),
        ).fetchone()
        if not row:
            return None
        return Entity(
            id=row["id"],
            name=row["name"],
            entity_type=row["entity_type"],
            description=row["description"],
            aliases=json.loads(row["aliases_json"] or "[]"),
            attributes=json.loads(row["attributes_json"] or "{}"),
            created_at=row["created_at"],
            user_id=row["user_id"],
        )

    def add_relation(
        self,
        source: str | Entity,
        target: str | Entity,
        relation_type: str,
        weight: float = 1.0,
        context: str = "",
        rel_id: str | None = None,
    ) -> Relation:
        """Create a directed relation between two entities."""
        src_ent = (
            source
            if isinstance(source, Entity)
            else (self.find_entity(source) or self.add_entity(source))
        )
        tgt_ent = (
            target
            if isinstance(target, Entity)
            else (self.find_entity(target) or self.add_entity(target))
        )

        # Check existing edge
        existing = self._conn.execute(
            """
            SELECT * FROM kg_relations
            WHERE source_id = ? AND target_id = ? AND relation_type = ? AND user_id = ?
            """,
            (src_ent.id, tgt_ent.id, relation_type, self.user_id),
        ).fetchone()

        now = time.time()
        if existing:
            new_weight = max(existing["weight"], weight)
            with self._conn:
                self._conn.execute(
                    "UPDATE kg_relations SET weight = ?, context = ? WHERE id = ?",
                    (new_weight, context or existing["context"], existing["id"]),
                )
            return Relation(
                id=existing["id"],
                source_id=src_ent.id,
                target_id=tgt_ent.id,
                relation_type=relation_type,
                weight=new_weight,
                context=context or existing["context"],
                created_at=existing["created_at"],
                user_id=self.user_id,
            )

        new_rel_id = rel_id or f"rel_{uuid.uuid4().hex[:10]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO kg_relations (
                    id, source_id, target_id, relation_type, weight,
                    context, created_at, user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_rel_id,
                    src_ent.id,
                    tgt_ent.id,
                    relation_type,
                    weight,
                    context,
                    now,
                    self.user_id,
                ),
            )
        return Relation(
            id=new_rel_id,
            source_id=src_ent.id,
            target_id=tgt_ent.id,
            relation_type=relation_type,
            weight=weight,
            context=context,
            created_at=now,
            user_id=self.user_id,
        )

    def extract_triples_from_text(self, text: str) -> list[tuple[str, str, str]]:
        """Extract entity-relation-entity triples via bilingual patterns."""
        triples: list[tuple[str, str, str]] = []

        # English patterns: "X uses Y", "X prefers Y", "X builds Y", "X works at Y"
        patterns_en = [
            (r"([A-Za-z0-9_\\-]+)\\s+(?:uses|is using)\\s+([A-Za-z0-9_\\-]+)", "uses"),
            (r"([A-Za-z0-9_\\-]+)\\s+(?:prefers|likes)\\s+([A-Za-z0-9_\\-]+)", "prefers"),
            (r"([A-Za-z0-9_\\-]+)\\s+(?:builds|develops|created)\\s+([A-Za-z0-9_\\-]+)", "builds"),
            (r"([A-Za-z0-9_\\-]+)\\s+(?:works at|works for)\\s+([A-Za-z0-9_\\-]+)", "works_at"),
            (r"([A-Za-z0-9_\\-]+)\\s+(?:is a|is an)\\s+([A-Za-z0-9_\\-]+)", "is_a"),
            (r"([A-Za-z0-9_\\-]+)\\s+(?:depends on)\\s+([A-Za-z0-9_\\-]+)", "depends_on"),
        ]

        # Persian patterns: "X با Y کار می‌کند", "X علاقه دارد به Y", "X سازنده Y است"
        patterns_fa = [
            (r"([\\w]+)\\s+(?:از|با)\\s+([\\w]+)\\s+(?:استفاده می‌کند|کار می‌کند)", "uses"),
            (r"([\\w]+)\\s+به\\s+([\\w]+)\\s+(?:علاقه دارد|ترجیح می‌دهد)", "prefers"),
            (r"([\\w]+)\\s+(?:سازنده|توسعه‌دهنده)\\s+([\\w]+)\\s+(?:است|هست)", "builds"),
            (r"([\\w]+)\\s+در\\s+([\\w]+)\\s+(?:کار می‌کند|شاغل است)", "works_at"),
        ]

        for pat, rel in patterns_en + patterns_fa:
            for match in re.finditer(pat, text, flags=re.IGNORECASE):
                src = match.group(1).strip()
                tgt = match.group(2).strip()
                if src and tgt and src.lower() != tgt.lower():
                    triples.append((src, rel, tgt))
        return triples

    def query_neighbors(
        self,
        entity_name: str,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """Multi-hop breadth-first graph traversal from root entity."""
        root = self.find_entity(entity_name)
        if not root:
            return []

        visited_nodes: set[str] = {root.id}
        queue: collections.deque[tuple[str, int]] = collections.deque([(root.id, 0)])
        paths: list[dict[str, Any]] = []

        while queue:
            current_id, hop = queue.popleft()
            if hop >= max_hops:
                continue

            # Outgoing edges
            rows_out = self._conn.execute(
                """
                SELECT r.*, e.name as target_name, e.entity_type as target_type
                FROM kg_relations r
                JOIN kg_entities e ON e.id = r.target_id
                WHERE r.source_id = ? AND r.user_id = ?
                """,
                (current_id, self.user_id),
            ).fetchall()

            curr_ent = self.get_entity_by_id(current_id)
            curr_name = curr_ent.name if curr_ent else current_id

            for row in rows_out:
                tgt_id = row["target_id"]
                paths.append(
                    {
                        "source": curr_name,
                        "relation": row["relation_type"],
                        "target": row["target_name"],
                        "hop": hop + 1,
                        "weight": row["weight"],
                        "context": row["context"],
                    }
                )
                if tgt_id not in visited_nodes:
                    visited_nodes.add(tgt_id)
                    queue.append((tgt_id, hop + 1))

        return paths

    def find_path(
        self,
        source_name: str,
        target_name: str,
        max_depth: int = 3,
    ) -> list[str] | None:
        """Find shortest relationship path between two entities."""
        src = self.find_entity(source_name)
        tgt = self.find_entity(target_name)
        if not src or not tgt:
            return None
        if src.id == tgt.id:
            return [src.name]

        queue: collections.deque[tuple[str, list[str]]] = collections.deque([(src.id, [src.name])])
        visited: set[str] = {src.id}

        while queue:
            curr_id, path = queue.popleft()
            if len(path) > max_depth + 1:
                continue

            rows = self._conn.execute(
                """
                SELECT r.relation_type, e.id as target_id, e.name as target_name
                FROM kg_relations r
                JOIN kg_entities e ON e.id = r.target_id
                WHERE r.source_id = ? AND r.user_id = ?
                """,
                (curr_id, self.user_id),
            ).fetchall()

            for row in rows:
                t_id = row["target_id"]
                step = f"--[{row['relation_type']}]--> {row['target_name']}"
                new_path = path + [step]
                if t_id == tgt.id:
                    return new_path
                if t_id not in visited:
                    visited.add(t_id)
                    queue.append((t_id, new_path))
        return None

    def export_ascii_graph(self) -> str:
        """Render knowledge graph as ASCII tree/table."""
        entities = self._conn.execute(
            "SELECT * FROM kg_entities WHERE user_id = ? ORDER BY name",
            (self.user_id,),
        ).fetchall()
        if not entities:
            return "Knowledge Graph is currently empty."

        lines = [f"📊 Knowledge Graph Memory ({len(entities)} Entities):"]
        for ent in entities:
            lines.append(f"  • Node: [{ent['entity_type']}] {ent['name']}")
            relations = self._conn.execute(
                """
                SELECT r.relation_type, e.name as target_name, r.weight
                FROM kg_relations r
                JOIN kg_entities e ON e.id = r.target_id
                WHERE r.source_id = ? AND r.user_id = ?
                """,
                (ent["id"], self.user_id),
            ).fetchall()
            for r in relations:
                edge_label = f"({r['relation_type']})"
                tgt = r["target_name"]
                w = r["weight"]
                lines.append(f"      └── {edge_label} ──> {tgt} [w={w:.1f}]")
        return "\\n".join(lines)
'''

RETRIEVAL_ENGINE = '''"""Unified Hybrid Retrieval & Knowledge Graph Memory Engine."""

from __future__ import annotations

import time
from typing import Any

from dream.retrieval.dense import DenseVectorStore
from dream.retrieval.fusion import HybridFusionEngine
from dream.retrieval.graph import KnowledgeGraphStore
from dream.retrieval.sparse import BM25Engine
from dream.retrieval.types import HybridSearchConfig, RetrievalResult


class UnifiedRetrievalEngine:
    """Combines BM25, Dense Cosine Search, RRF Fusion, and Knowledge Graph Traversal."""

    def __init__(
        self,
        config: HybridSearchConfig | None = None,
        db_path: str | None = None,
        user_id: str = "default",
    ) -> None:
        self.config = config or HybridSearchConfig()
        self.user_id = user_id
        self.bm25 = BM25Engine()
        self.vector_store = DenseVectorStore()
        self.fusion = HybridFusionEngine(self.config)
        self.graph = KnowledgeGraphStore(db_path=db_path, user_id=user_id)
        self.documents: dict[str, str] = {}
        self.metadata: dict[str, dict[str, Any]] = {}

    def index_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        extract_triples: bool = True,
    ) -> None:
        """Add document to both sparse and dense stores and extract knowledge triples."""
        meta = metadata or {}
        if "created_at" not in meta:
            meta["created_at"] = time.time()

        self.documents[doc_id] = content
        self.metadata[doc_id] = meta

        # 1. Sparse BM25
        self.bm25.add_document(doc_id, content, meta)

        # 2. Dense Vector Store
        self.vector_store.add_document(doc_id, content, metadata=meta)

        # 3. Knowledge Graph extraction
        if extract_triples:
            triples = self.graph.extract_triples_from_text(content)
            for src, rel, tgt in triples:
                self.graph.add_relation(source=src, target=tgt, relation_type=rel, context=content)

    def remove_document(self, doc_id: str) -> None:
        """Remove document from all indexing structures."""
        self.documents.pop(doc_id, None)
        self.metadata.pop(doc_id, None)
        self.bm25.remove_document(doc_id)
        self.vector_store.remove_document(doc_id)

    def search(
        self,
        query: str,
        top_k: int = 5,
        include_graph_context: bool = True,
        current_time: float | None = None,
    ) -> list[RetrievalResult]:
        """Perform hybrid dense+sparse recall with graph-boosted RRF ranking."""
        if not self.documents:
            return []

        # 1. Sparse hits
        sparse_hits = self.bm25.search(query, top_k=top_k * 3)

        # 2. Dense hits
        dense_hits = self.vector_store.search(query, top_k=top_k * 3)

        # 3. Graph traversal & entity boosts
        graph_boosts: dict[str, float] = {}
        matched_entities: list[str] = []

        if include_graph_context:
            for word in query.split():
                clean = word.strip("?,.!:;()[]{}").lower()
                if len(clean) > 2:
                    ent = self.graph.find_entity(clean)
                    if ent:
                        matched_entities.append(ent.name)
                        neighbors = self.graph.query_neighbors(
                            ent.name, max_hops=self.config.graph_hop_limit
                        )
                        for doc_id, text in self.documents.items():
                            for n in neighbors:
                                if n["target"].lower() in text.lower():
                                    graph_boosts[doc_id] = graph_boosts.get(doc_id, 0.0) + 0.05

        # 4. Hybrid rank fusion
        fused_results = self.fusion.fuse(
            sparse_hits=sparse_hits,
            dense_hits=dense_hits,
            doc_store=self.documents,
            doc_metadata=self.metadata,
            top_k=top_k,
            current_time=current_time,
            graph_boosts=graph_boosts,
        )

        # 5. Attach graph context
        if include_graph_context and matched_entities:
            for res in fused_results:
                res.related_entities = matched_entities
                for ent_name in matched_entities:
                    neighbors = self.graph.query_neighbors(
                        ent_name, max_hops=self.config.graph_hop_limit
                    )
                    for n in neighbors:
                        line = f"({n['source']}) ──[{n['relation']}]──> ({n['target']})"
                        if line not in res.graph_context:
                            res.graph_context.append(line)

        return fused_results
'''

RETRIEVAL_TOOLS = '''"""Agent tool definitions for hybrid semantic search and knowledge graph memory."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from dream.retrieval.engine import UnifiedRetrievalEngine

_GLOBAL_ENGINE: UnifiedRetrievalEngine | None = None


def get_global_retrieval_engine() -> UnifiedRetrievalEngine:
    """Retrieve or initialize singleton retrieval engine."""
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = UnifiedRetrievalEngine()
    return _GLOBAL_ENGINE


def set_global_retrieval_engine(engine: UnifiedRetrievalEngine) -> None:
    """Set global retrieval engine instance."""
    global _GLOBAL_ENGINE
    _GLOBAL_ENGINE = engine


def search_hybrid_memory(query: str, limit: int = 5) -> str:
    """Perform hybrid BM25 + Dense Semantic search across agent associative memory.

    Args:
        query: Search query in English or Persian.
        limit: Max number of relevant memories to retrieve (default 5).

    Returns:
        JSON string containing ranked memories with relevance scores and graph links.
    """
    engine = get_global_retrieval_engine()
    results = engine.search(query, top_k=limit)
    if not results:
        return json.dumps(
            {"status": "empty", "query": query, "results": []},
            ensure_ascii=False,
        )

    formatted = []
    for r in results:
        formatted.append(
            {
                "doc_id": r.doc_id,
                "content": r.content,
                "score": round(r.score, 4),
                "breakdown": {
                    "bm25_score": round(r.breakdown.sparse_bm25_score, 3),
                    "vector_score": round(r.breakdown.dense_vector_score, 3),
                    "rrf_score": round(r.breakdown.rrf_score, 4),
                    "temporal_decay": round(r.breakdown.temporal_multiplier, 3),
                },
                "graph_associations": r.graph_context,
            }
        )

    return json.dumps(
        {"status": "ok", "query": query, "count": len(formatted), "results": formatted},
        ensure_ascii=False,
        indent=2,
    )


def query_knowledge_graph(entity_name: str, max_hops: int = 2) -> str:
    """Query relationships and multi-hop semantic links for an entity in Knowledge Graph.

    Args:
        entity_name: Target entity name (e.g. 'Ali', 'Dream', 'Python').
        max_hops: Exploration depth (1 or 2 hops).

    Returns:
        JSON string describing entity details and related knowledge graph paths.
    """
    engine = get_global_retrieval_engine()
    entity = engine.graph.find_entity(entity_name)
    if not entity:
        return json.dumps(
            {
                "status": "not_found",
                "entity": entity_name,
                "message": f"Entity '{entity_name}' not found in knowledge graph.",
            },
            ensure_ascii=False,
        )

    neighbors = engine.graph.query_neighbors(entity.name, max_hops=max_hops)
    return json.dumps(
        {
            "status": "ok",
            "entity": {
                "id": entity.id,
                "name": entity.name,
                "type": entity.entity_type,
                "description": entity.description,
                "aliases": entity.aliases,
            },
            "relationships_count": len(neighbors),
            "relationships": neighbors,
        },
        ensure_ascii=False,
        indent=2,
    )


def get_retrieval_tools() -> dict[str, Callable[..., Any]]:
    """Return dict of retrieval tools for registration."""
    return {
        "search_hybrid_memory": search_hybrid_memory,
        "query_knowledge_graph": query_knowledge_graph,
    }
'''

RETRIEVAL_SLASH = '''"""Slash command handlers for Knowledge Graph Memory and Hybrid Retrieval."""

from __future__ import annotations

from collections.abc import Callable

from dream.retrieval.engine import UnifiedRetrievalEngine
from dream.retrieval.tools import get_global_retrieval_engine
from dream.tui.colors import ColorManager


def handle_graph_command(
    cmd_text: str,
    engine: UnifiedRetrievalEngine | None = None,
    output: Callable[[str], None] = print,
    colors: ColorManager | None = None,
) -> bool:
    """Handle `/graph` slash command (inspect, query entity, or find paths)."""
    cm = colors or ColorManager()
    eng = engine or get_global_retrieval_engine()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "show"

    if subcmd in ("show", "list", "view"):
        ascii_view = eng.graph.export_ascii_graph()
        output(cm.cyan(ascii_view))
        return True

    if subcmd in ("entity", "node", "query") and len(parts) > 2:
        name = parts[2]
        entity = eng.graph.find_entity(name)
        if not entity:
            output(cm.yellow(f"Entity '{name}' not found in knowledge graph."))
            return True
        output(cm.bold(f"Node: [{entity.entity_type}] {entity.name}"))
        if entity.description:
            output(f"  Description: {entity.description}")
        if entity.aliases:
            output(f"  Aliases: {', '.join(entity.aliases)}")
        neighbors = eng.graph.query_neighbors(entity.name, max_hops=2)
        if neighbors:
            output(cm.dim("  Connections:"))
            for n in neighbors:
                output(f"    • ({n['source']}) ──[{n['relation']}]──> ({n['target']})")
        return True

    if subcmd in ("path", "link") and len(parts) > 3:
        src, tgt = parts[2], parts[3]
        path = eng.graph.find_path(src, tgt)
        if not path:
            output(cm.yellow(f"No semantic path found between '{src}' and '{tgt}'."))
            return True
        output(cm.bold(f"Path between {src} and {tgt}:"))
        output("  " + " ".join(path))
        return True

    # Usage help
    output(cm.bold("Usage / راهنمای دستور /graph:"))
    output("  /graph                  - نمایش گراف دانش متنی / Show ASCII graph")
    output("  /graph entity <name>    - جستجوی یک گره / Inspect entity node")
    output("  /graph path <src> <tgt> - یافتن کوتاهترین مسیر / Find shortest path")
    return True


def handle_retrieve_command(
    cmd_text: str,
    engine: UnifiedRetrievalEngine | None = None,
    output: Callable[[str], None] = print,
    colors: ColorManager | None = None,
) -> bool:
    """Handle `/retrieve` slash command (test hybrid search with scoring breakdown)."""
    cm = colors or ColorManager()
    eng = engine or get_global_retrieval_engine()
    parts = cmd_text.strip().split(maxsplit=1)
    if len(parts) < 2:
        output(cm.yellow("Usage: /retrieve <search query>"))
        return True

    query = parts[1]
    results = eng.search(query, top_k=5)
    if not results:
        output(cm.dim(f"No matching documents found for query: '{query}'"))
        return True

    output(cm.bold(f"Hybrid Retrieval Results for '{query}' (Found {len(results)}):"))
    for idx, r in enumerate(results, 1):
        b = r.breakdown
        score_str = (
            f"Final: {r.score:.4f} [BM25: {b.sparse_bm25_score:.2f} (# {b.sparse_bm25_rank}) | "
            f"Dense: {b.dense_vector_score:.2f} (# {b.dense_vector_rank}) | "
            f"Decay: {b.temporal_multiplier:.2f}]"
        )
        output(f"  {idx}. {cm.green(r.content)}")
        output(f"     {cm.dim(score_str)}")
        if r.graph_context:
            output(f"     {cm.cyan('Graph Links:')} {'; '.join(r.graph_context[:2])}")

    return True
'''

RETRIEVAL_INIT = '''"""Dream Hybrid Semantic Retrieval & Knowledge Graph Memory subsystem."""

from __future__ import annotations

from dream.retrieval.dense import DenseVectorStore, cosine_similarity, generate_pseudo_embedding
from dream.retrieval.engine import UnifiedRetrievalEngine
from dream.retrieval.fusion import HybridFusionEngine, compute_temporal_decay
from dream.retrieval.graph import KnowledgeGraphStore
from dream.retrieval.slash import handle_graph_command, handle_retrieve_command
from dream.retrieval.sparse import BM25Engine, tokenize_bilingual
from dream.retrieval.tools import (
    get_global_retrieval_engine,
    get_retrieval_tools,
    query_knowledge_graph,
    search_hybrid_memory,
    set_global_retrieval_engine,
)
from dream.retrieval.types import (
    Entity,
    HybridSearchConfig,
    Relation,
    RetrievalResult,
    RetrievalScoreBreakdown,
)

__all__ = [
    "BM25Engine",
    "DenseVectorStore",
    "Entity",
    "HybridFusionEngine",
    "HybridSearchConfig",
    "KnowledgeGraphStore",
    "Relation",
    "RetrievalResult",
    "RetrievalScoreBreakdown",
    "UnifiedRetrievalEngine",
    "compute_temporal_decay",
    "cosine_similarity",
    "generate_pseudo_embedding",
    "get_global_retrieval_engine",
    "get_retrieval_tools",
    "handle_graph_command",
    "handle_retrieve_command",
    "query_knowledge_graph",
    "search_hybrid_memory",
    "set_global_retrieval_engine",
    "tokenize_bilingual",
]
'''

TOOLSETS_PY = '''"""Toolset categorization, grouping, and dynamic tool management."""

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
        description="Reusable skill management and lifecycle",
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
'''

TEST_RETRIEVAL = '''"""Comprehensive test suite for Hybrid Semantic Retrieval & Knowledge Graph Memory."""

from __future__ import annotations

import json

from dream.retrieval import (
    BM25Engine,
    DenseVectorStore,
    HybridFusionEngine,
    HybridSearchConfig,
    KnowledgeGraphStore,
    UnifiedRetrievalEngine,
    compute_temporal_decay,
    cosine_similarity,
    generate_pseudo_embedding,
    get_retrieval_tools,
    handle_graph_command,
    handle_retrieve_command,
    query_knowledge_graph,
    search_hybrid_memory,
    set_global_retrieval_engine,
    tokenize_bilingual,
)
from dream.tools.toolsets import get_toolset


def test_sparse_bm25_tokenization_and_search():
    """Verify bilingual BM25 tokenization, document indexing, and ranking."""
    engine = BM25Engine()

    # Bilingual Persian and English tokens
    tokens = tokenize_bilingual("Ali builds the Dream assistant in Python با هوش مصنوعی")
    assert "ali" in tokens
    assert "dream" in tokens
    assert "python" in tokens
    assert "هوش" in tokens
    assert "مصنوعی" in tokens

    # Add documents
    engine.add_document("doc1", "Python is an amazing programming language for AI agents.")
    engine.add_document("doc2", "دستیار هوشمند دریم بر پایه پایتون توسعه داده شده است.")
    engine.add_document("doc3", "Cooking Italian pizza with tomato and mozzarella cheese.")

    assert engine.doc_count == 3

    # English query
    hits_en = engine.search("Python AI programming", top_k=2)
    assert len(hits_en) > 0
    assert hits_en[0][0] == "doc1"

    # Persian query
    hits_fa = engine.search("دستیار هوشمند پایتون", top_k=2)
    assert len(hits_fa) > 0
    assert hits_fa[0][0] == "doc2"

    # Remove document
    engine.remove_document("doc1")
    assert engine.doc_count == 2
    assert "doc1" not in engine.doc_contents


def test_dense_vector_store_and_cosine_similarity():
    """Verify normalized pseudo-embedding generation and cosine similarity search."""
    store = DenseVectorStore(embed_dim=64)

    v1 = generate_pseudo_embedding("Python AI Agent", dim=64)
    v2 = generate_pseudo_embedding("Python Artificial Intelligence Agent", dim=64)
    v3 = generate_pseudo_embedding("Baking chocolate cake", dim=64)

    sim_high = cosine_similarity(v1, v2)
    sim_low = cosine_similarity(v1, v3)
    assert sim_high > sim_low

    # Index into dense vector store
    store.add_document("d1", "Machine learning and deep neural networks")
    store.add_document("d2", "How to bake sourdough bread at home")

    results = store.search("Neural network learning models", top_k=1)
    assert len(results) == 1
    assert results[0][0] == "d1"
    assert results[0][1] > 0.5


def test_hybrid_fusion_and_temporal_decay():
    """Verify RRF rank fusion and exponential temporal decay calculation."""
    # Temporal decay test
    now = 1000000.0
    created_recent = now - (86400.0 * 5)  # 5 days old
    created_old = now - (86400.0 * 60)  # 60 days old

    decay_recent = compute_temporal_decay(created_recent, half_life_days=30.0, current_time=now)
    decay_old = compute_temporal_decay(created_old, half_life_days=30.0, current_time=now)
    assert decay_recent > decay_old
    assert 0.8 < decay_recent < 1.0
    assert 0.2 < decay_old < 0.4

    # Fusion test
    config = HybridSearchConfig(fusion_mode="rrf", rrf_k=60)
    fusion = HybridFusionEngine(config)

    sparse_hits = [("doc1", 2.5), ("doc2", 1.2)]
    dense_hits = [("doc2", 0.95), ("doc1", 0.80)]
    doc_store = {"doc1": "Content 1", "doc2": "Content 2"}
    metadata = {
        "doc1": {"created_at": now - 1000},
        "doc2": {"created_at": now - 1000},
    }

    fused = fusion.fuse(
        sparse_hits=sparse_hits,
        dense_hits=dense_hits,
        doc_store=doc_store,
        doc_metadata=metadata,
        top_k=2,
        current_time=now,
    )
    assert len(fused) == 2
    assert fused[0].doc_id in ("doc1", "doc2")
    assert fused[0].breakdown.rrf_score > 0.0


def test_knowledge_graph_crud_and_traversal(tmp_path):
    """Verify Knowledge Graph entities, relations, pattern extraction, and multi-hop paths."""
    db_file = str(tmp_path / "kg_test.db")
    kg = KnowledgeGraphStore(db_path=db_file, user_id="u1")

    # Add entity
    ent1 = kg.add_entity(
        name="Ali",
        entity_type="person",
        description="Lead developer",
        aliases=["Ali Naderi", "Developer"],
    )
    ent2 = kg.add_entity(name="Dream", entity_type="project", description="Next-Gen Agent")
    ent3 = kg.add_entity(name="Python", entity_type="tool", description="Programming Language")

    assert ent1.matches("Ali Naderi")
    assert ent1.matches("ali")
    assert not ent1.matches("John")

    # Add relations
    kg.add_relation(source=ent1, target=ent2, relation_type="builds", weight=1.0)
    kg.add_relation(source=ent2, target=ent3, relation_type="uses", weight=0.9)

    # Multi-hop neighbors
    neighbors = kg.query_neighbors("Ali", max_hops=2)
    assert len(neighbors) == 2
    targets = {n["target"] for n in neighbors}
    assert "Dream" in targets
    assert "Python" in targets

    # Path finding
    path = kg.find_path("Ali", "Python", max_depth=3)
    assert path is not None
    assert len(path) == 3
    assert path[0] == "Ali"
    assert "uses" in path[2]

    # Pattern extraction
    text = "Ali builds Dream and uses Python daily for work."
    triples = kg.extract_triples_from_text(text)
    assert len(triples) >= 1
    assert any(t[1] in ("builds", "uses") for t in triples)

    # ASCII Export
    ascii_graph = kg.export_ascii_graph()
    assert "Knowledge Graph Memory" in ascii_graph
    assert "Ali" in ascii_graph
    assert "Dream" in ascii_graph


def test_unified_retrieval_engine_and_graph_boost(tmp_path):
    """Verify UnifiedRetrievalEngine end-to-end flow with graph boosting."""
    db_file = str(tmp_path / "unified_kg.db")
    engine = UnifiedRetrievalEngine(db_path=db_file)

    engine.index_document(
        doc_id="mem1",
        content="Ali works at Dream AI and develops memory retrieval architecture.",
        metadata={"pinned": True},
    )
    engine.index_document(
        doc_id="mem2",
        content="Weather forecast in Tehran shows clear sky and moderate temperature.",
    )

    # Search with hybrid query
    results = engine.search("Who develops Dream AI architecture?", top_k=1)
    assert len(results) == 1
    assert results[0].doc_id == "mem1"
    assert results[0].metadata["pinned"] is True


def test_retrieval_tools_and_slash_commands(tmp_path):
    """Verify tool execution and slash commands for retrieval and graph."""
    db_file = str(tmp_path / "tools_kg.db")
    engine = UnifiedRetrievalEngine(db_path=db_file)
    set_global_retrieval_engine(engine)

    engine.index_document(
        doc_id="item1",
        content="Dream agent uses SQLite for local encrypted persistent storage.",
    )

    # Tool: search_hybrid_memory
    search_json = search_hybrid_memory("SQLite persistent storage", limit=2)
    parsed_search = json.loads(search_json)
    assert parsed_search["status"] == "ok"
    assert parsed_search["count"] >= 1

    # Tool: query_knowledge_graph
    graph_json = query_knowledge_graph("Dream", max_hops=2)
    parsed_graph = json.loads(graph_json)
    assert parsed_graph["status"] in ("ok", "not_found")

    # Tool dict registration
    tools_dict = get_retrieval_tools()
    assert "search_hybrid_memory" in tools_dict
    assert "query_knowledge_graph" in tools_dict

    # Slash commands
    out: list[str] = []
    handle_graph_command("/graph", engine=engine, output=out.append)
    assert any("Knowledge Graph" in line for line in out)

    out.clear()
    handle_retrieve_command("/retrieve SQLite storage", engine=engine, output=out.append)
    assert any("Hybrid Retrieval Results" in line for line in out)


def test_toolsets_includes_retrieval():
    """Verify retrieval toolset registration in BUILTIN_TOOLSETS."""
    retrieval_ts = get_toolset("retrieval")
    assert retrieval_ts is not None
    assert "search_hybrid_memory" in retrieval_ts.tools
    assert "query_knowledge_graph" in retrieval_ts.tools
'''


def apply_patch(repo_dir: Path) -> None:
    print(f"[*] Applying PR #18 (Hybrid Semantic Retrieval & Knowledge Graph Memory) to: {repo_dir.resolve()}")

    files_to_write = {
        repo_dir / "dream" / "retrieval" / "__init__.py": RETRIEVAL_INIT,
        repo_dir / "dream" / "retrieval" / "types.py": RETRIEVAL_TYPES,
        repo_dir / "dream" / "retrieval" / "sparse.py": RETRIEVAL_SPARSE,
        repo_dir / "dream" / "retrieval" / "dense.py": RETRIEVAL_DENSE,
        repo_dir / "dream" / "retrieval" / "fusion.py": RETRIEVAL_FUSION,
        repo_dir / "dream" / "retrieval" / "graph.py": RETRIEVAL_GRAPH,
        repo_dir / "dream" / "retrieval" / "engine.py": RETRIEVAL_ENGINE,
        repo_dir / "dream" / "retrieval" / "tools.py": RETRIEVAL_TOOLS,
        repo_dir / "dream" / "retrieval" / "slash.py": RETRIEVAL_SLASH,
        repo_dir / "dream" / "tools" / "toolsets.py": TOOLSETS_PY,
        repo_dir / "tests" / "test_retrieval_and_knowledge_graph.py": TEST_RETRIEVAL,
    }

    for path, content in files_to_write.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"  [+] Wrote: {path.relative_to(repo_dir)}")

    print("\n[✓] PR #18 successfully applied!")
    print("Next steps:")
    print("  1. Run tests: pytest -v tests/test_retrieval_and_knowledge_graph.py")
    print("  2. Run linter: ruff check dream/retrieval dream/tools/toolsets.py tests/test_retrieval_and_knowledge_graph.py")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    apply_patch(target)
