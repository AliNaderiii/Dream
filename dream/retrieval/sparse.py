"""BM25 sparse retrieval engine supporting bilingual Persian and English indexing."""

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
    tokens = re.findall(r"[\w]+", norm.lower(), flags=re.UNICODE)
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
