"""Multi-tier semantic cache with exact hashing, token similarity, and TTL eviction."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

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
