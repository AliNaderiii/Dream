"""Unified Hybrid Retrieval & Knowledge Graph Memory Engine."""

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
