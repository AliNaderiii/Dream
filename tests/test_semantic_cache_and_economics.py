"""Unit and integration tests for Semantic Caching, Speculative Execution, and Token Economics."""

from __future__ import annotations

from pathlib import Path
import tempfile
import time
import pytest

from dream.cache import (
    CacheEconomics,
    CacheEngine,
    CacheTier,
    SemanticCache,
    SpeculativePrefetcher,
    cache_clear,
    cache_get_economics,
    cache_lookup_query,
    cache_predict_tool,
    cache_store_entry,
    cache_warmup,
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
    cache.store(
        query="\u0686\u06af\u0648\u0646\u0647 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u0645 \u067e\u0627\u06cc\u062a\u0648\u0646 \u06cc\u0627\u062f \u0628\u06af\u06cc\u0631\u0645\u061f",
        response="\u0628\u0631\u0627\u06cc \u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc \u067e\u0627\u06cc\u062a\u0648\u0646 \u0627\u0632 \u062f\u0648\u0631\u0647\u200c\u0647\u0627\u06cc \u0622\u0646\u0644\u0627\u06cc\u0646 \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f.",
        tokens_saved=120,
    )

    # 1. Exact match (with slight spacing / normalization difference)
    hit1 = cache.lookup("\u0686\u06af\u0648\u0646\u0647 \u0645\u06cc \u062a\u0648\u0627\u0646\u0645 \u067e\u0627\u06cc\u062a\u0648\u0646 \u06cc\u0627\u062f \u0628\u06af\u06cc\u0631\u0645")
    assert hit1 is not None
    assert hit1.tier == CacheTier.L1_EXACT
    assert hit1.similarity_score >= 0.99

    # 2. Semantic fuzzy match
    hit2 = cache.lookup("\u0686\u0637\u0648\u0631 \u067e\u0627\u06cc\u062a\u0648\u0646 \u06cc\u0627\u062f \u0628\u06af\u06cc\u0631\u0645\u061f", similarity_threshold=0.60)
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
    pred_time = prefetcher.predict_tool("\u0627\u0644\u0627\u0646 \u0633\u0627\u0639\u062a \u0686\u0646\u062f\u0647\u061f")
    assert pred_time is not None
    assert pred_time.predicted_tool == "get_datetime"

    # Notes prediction
    pred_notes = prefetcher.predict_tool("\u0644\u0637\u0641\u0627 \u0644\u06cc\u0633\u062a \u06cc\u0627\u062f\u062f\u0627\u0634\u062a \u0647\u0627 \u0631\u0648 \u0646\u0634\u0648\u0646 \u0628\u062f\u0647")
    assert pred_notes is not None
    assert pred_notes.predicted_tool == "list_notes"

    # Non-matching prompt
    pred_none = prefetcher.predict_tool("Write a python script for neural ODEs")
    assert pred_none is None


def test_cache_engine_and_token_economics() -> None:
    """Verify end-to-end cache engine, token savings calculation, and disk persistence."""
    engine = CacheEngine()

    # Warmup queries exist
    hit_warm = engine.query("\u0633\u0644\u0627\u0645")
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
    lookup_res = cache_lookup_query("\u0633\u0644\u0627\u0645")
    assert lookup_res["hit"] is True

    # Tool: predict
    pred_res = cache_predict_tool("\u0633\u0627\u0639\u062a \u0686\u0646\u062f\u0647")
    assert pred_res["predicted"] is True

    # Tool: economics
    econ_res = cache_get_economics()
    assert econ_res["success"] is True
    assert "total_tokens_saved" in econ_res

    # Slash: stats
    stats_msg = handle_cache_slash_command("/cache stats")
    assert "USD" in stats_msg

    # Slash: lookup
    lookup_msg = handle_cache_slash_command("/cache lookup \u0633\u0644\u0627\u0645")
    assert "\u0627\u0635\u0627\u0628\u062a \u0628\u0647 \u06a9\u0634" in lookup_msg

    # Slash: clear
    clear_msg = handle_cache_slash_command("/cache clear")
    assert "\u067e\u0627\u06a9\u0633\u0627\u0632\u06cc" in clear_msg
