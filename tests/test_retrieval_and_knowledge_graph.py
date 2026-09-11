"""Comprehensive test suite for Hybrid Semantic Retrieval & Knowledge Graph Memory."""

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
