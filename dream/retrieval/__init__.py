"""Dream Hybrid Semantic Retrieval & Knowledge Graph Memory subsystem."""

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
