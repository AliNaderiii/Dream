"""Unit and integration tests for Semantic Caching, Speculative Execution & Token Economics."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from dream.cache import (
    CacheEngine,
    CacheTier,
    SemanticCache,
    SpeculativePrefetcher,
    cache_get_economics,
    cache_lookup_query,
    cache_predict_tool,
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
    q_store = "چگونه می‌توانم پایتون یاد بگیرم؟"
    r_store = "برای یادگیری پایتون از دوره‌های آنلاین استفاده کنید."
    cache.store(
        query=q_store,
        response=r_store,
        tokens_saved=120,
    )

    # 1. Exact match (with slight spacing / normalization difference)
    q_lookup1 = "چگونه می توانم پایتون یاد بگیرم"
    hit1 = cache.lookup(q_lookup1)
    assert hit1 is not None
    assert hit1.tier == CacheTier.L1_EXACT
    assert hit1.similarity_score >= 0.99

    # 2. Semantic fuzzy match
    q_lookup2 = "چطور پایتون یاد بگیرم؟"
    hit2 = cache.lookup(q_lookup2, similarity_threshold=0.60)
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
    pred_time = prefetcher.predict_tool("الان ساعت چنده؟")
    assert pred_time is not None
    assert pred_time.predicted_tool == "get_datetime"

    # Notes prediction
    pred_notes = prefetcher.predict_tool("لطفا لیست یادداشت ها رو نشون بده")
    assert pred_notes is not None
    assert pred_notes.predicted_tool == "list_notes"

    # Non-matching prompt
    pred_none = prefetcher.predict_tool("Write a python script for neural ODEs")
    assert pred_none is None


def test_cache_engine_and_token_economics() -> None:
    """Verify end-to-end cache engine, token savings calculation, and disk persistence."""
    engine = CacheEngine()

    # Warmup queries exist
    hit_warm = engine.query("سلام")
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
    lookup_res = cache_lookup_query("سلام")
    assert lookup_res["hit"] is True

    # Tool: predict
    pred_res = cache_predict_tool("ساعت چنده")
    assert pred_res["predicted"] is True

    # Tool: economics
    econ_res = cache_get_economics()
    assert econ_res["success"] is True
    assert "total_tokens_saved" in econ_res

    # Slash: stats
    stats_msg = handle_cache_slash_command("/cache stats")
    assert "USD" in stats_msg

    # Slash: lookup
    lookup_msg = handle_cache_slash_command("/cache lookup سلام")
    assert "اصابت به کش" in lookup_msg

    # Slash: clear
    clear_msg = handle_cache_slash_command("/cache clear")
    assert "پاکسازی" in clear_msg
