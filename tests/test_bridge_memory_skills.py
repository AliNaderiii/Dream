"""Tests for the memory/skills explorer RPC methods added in P-05.

These exercise the new ``memory.list`` (filters/sort/pagination),
``memory.count``, ``memory.create``, and the skill enable/disable/delete/
export/install-with-validation surface. They must not touch the durable
storage backends (``dream/memory.py`` / ``dream/skills.py``) — only consume
their public API.
"""

from __future__ import annotations

import json
import tempfile

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore


def make_methods(tmp_path) -> BridgeMethods:
    store = MemoryStore(":memory:")
    return BridgeMethods(
        store,
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        disabled_skills_path=str(tmp_path / "disabled.json"),
        default_provider="echo",
    )


# --------------------------------------------------------------------------- #
# memory.list / count / create
# --------------------------------------------------------------------------- #


def test_memory_list_pagination_and_filters(tmp_path):
    m = make_methods(tmp_path)
    m.store.remember("semantic alpha coffee", kind="semantic", importance=0.9)
    m.store.remember("episodic beta event", kind="episodic", importance=0.2)
    m.store.remember("procedural gamma step", kind="procedural", importance=0.5)

    # Default list returns everything, newest first.
    out = m.memory_list({})
    assert out["total"] == 3
    assert out["has_more"] is False
    assert out["next_cursor"] is None
    assert len(out["memories"]) == 3

    # Kind filter.
    filtered = m.memory_list({"kind_filter": "episodic"})
    assert filtered["total"] == 1
    assert filtered["memories"][0]["kind"] == "episodic"

    # Search query (Persian-aware normalised substring).
    searched = m.memory_list({"search_query": "coffee"})
    assert searched["total"] == 1
    assert "coffee" in searched["memories"][0]["content"]

    # Importance minimum filter.
    imp = m.memory_list({"min_importance": 0.8})
    assert imp["total"] == 1

    # Pagination with small page size.
    page1 = m.memory_list({"limit": 2})
    assert len(page1["memories"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"] == "2"
    page2 = m.memory_list({"limit": 2, "cursor": page1["next_cursor"]})
    assert len(page2["memories"]) == 1
    assert page2["has_more"] is False
    assert page2["next_cursor"] is None

    # Sort by importance (desc).
    by_imp = m.memory_list({"sort_by": "importance"})
    assert by_imp["memories"][0]["importance"] >= by_imp["memories"][-1]["importance"]


def test_memory_list_rejects_bad_params(tmp_path):
    m = make_methods(tmp_path)
    with pytest.raises(BridgeError):
        m.memory_list({"kind_filter": "bogus"})
    with pytest.raises(BridgeError):
        m.memory_list({"sort_by": "nonsense"})
    with pytest.raises(BridgeError):
        m.memory_list({"limit": 0})


def test_memory_count_by_kind(tmp_path):
    m = make_methods(tmp_path)
    m.store.remember("a", kind="semantic")
    m.store.remember("b", kind="semantic")
    m.store.remember("c", kind="episodic")
    counts = m.memory_count({})
    assert counts["total"] == 3
    assert counts["by_kind"]["semantic"] == 2
    assert counts["by_kind"]["episodic"] == 1
    assert counts["by_kind"]["procedural"] == 0


def test_memory_create_validates(tmp_path):
    m = make_methods(tmp_path)
    created = m.memory_create(
        {"content": "I prefer tea", "kind": "semantic", "importance": 0.7, "tags": ["drink"]}
    )
    assert created["memory"]["content"] == "I prefer tea"
    assert created["memory"]["importance"] == 0.7
    assert "drink" in created["memory"]["tags"]

    # Empty content rejected.
    with pytest.raises(BridgeError):
        m.memory_create({"content": "   "})
    # Oversize content rejected.
    with pytest.raises(BridgeError):
        m.memory_create({"content": "x" * (60 * 1024)})
    # Bad importance rejected.
    with pytest.raises(BridgeError):
        m.memory_create({"content": "ok", "importance": 5.0})
    # HTML/script sanitised on create.
    sanitised = m.memory_create(
        {"content": "safe text <script>alert(1)</script> and <b>bold</b>"}
    )
    assert "<script>" not in sanitised["memory"]["content"]
    assert "<b>" not in sanitised["memory"]["content"]
    assert "safe text" in sanitised["memory"]["content"]
    assert "and bold" in sanitised["memory"]["content"]


# --------------------------------------------------------------------------- #
# skill enable / disable / delete / export / install
# --------------------------------------------------------------------------- #


def test_skill_enable_disable_round_trip(tmp_path, monkeypatch):
    import dream.tools as tools_mod

    monkeypatch.setattr(tools_mod, "WORKSPACE_ROOT", tmp_path)

    m = make_methods(tmp_path)
    m.skill_install(
        {"name": "brewing", "description": "brew coffee", "steps": ["grind", "pour"]}
    )

    listed = m.skill_list({})
    assert listed["skills"][0]["enabled"] is True

    disabled = m.skill_disable({"skill_id": "brewing"})
    assert disabled["enabled"] is False
    listed2 = m.skill_list({})
    assert listed2["skills"][0]["enabled"] is False

    # Disable state persists to disk.
    raw = json.loads((tmp_path / "disabled.json").read_text(encoding="utf-8"))
    assert "brewing" in raw

    enabled = m.skill_enable({"skill_id": "brewing"})
    assert enabled["enabled"] is True
    listed3 = m.skill_list({})
    assert listed3["skills"][0]["enabled"] is True


def test_skill_get_detail_and_export(tmp_path, monkeypatch):
    import dream.tools as tools_mod

    monkeypatch.setattr(tools_mod, "WORKSPACE_ROOT", tmp_path)

    m = make_methods(tmp_path)
    m.skill_install(
        {"name": "tea", "description": "make tea", "steps": ["boil", "steep"]}
    )

    detail = m.skill_get({"skill_id": "tea"})
    assert detail["match"]["name"] == "tea"
    assert detail["match"]["enabled"] is True
    assert "name: tea" in detail["match"]["content"]
    assert detail["match"]["created_at"] > 0

    exported = m.skill_export({"skill_id": "tea"})
    assert exported["content"].startswith("name: tea")
    assert exported["filename"].endswith(".txt")


def test_skill_delete_and_unknown(tmp_path, monkeypatch):
    import dream.tools as tools_mod

    monkeypatch.setattr(tools_mod, "WORKSPACE_ROOT", tmp_path)

    m = make_methods(tmp_path)
    m.skill_install({"name": "x", "description": "d", "steps": ["s"]})
    out = m.skill_delete({"skill_id": "x"})
    assert out["deleted"] is True
    assert m.skill_list({})["skills"] == []

    with pytest.raises(BridgeError):
        m.skill_delete({"skill_id": "does-not-exist"})


def test_skill_install_from_content_and_conflict(tmp_path, monkeypatch):
    import dream.tools as tools_mod

    monkeypatch.setattr(tools_mod, "WORKSPACE_ROOT", tmp_path)

    m = make_methods(tmp_path)
    body = "name: import test\ndescription: does a thing\nsteps:\n1. first\n2. second\n"
    installed = m.skill_install({"content": body})
    assert installed["status"] == "installed"
    assert installed["name"] == "import test"

    # Re-installing the same name without overwrite reports a conflict.
    again = m.skill_install({"content": body})
    assert again["status"] == "conflict"
    assert again["conflict"] is True

    # Overwrite resolves it.
    overwritten = m.skill_install({"content": body, "overwrite": True})
    assert overwritten["status"] == "installed"


def test_skill_install_rejects_malicious_content(tmp_path, monkeypatch):
    import dream.tools as tools_mod

    monkeypatch.setattr(tools_mod, "WORKSPACE_ROOT", tmp_path)

    m = make_methods(tmp_path)
    # Absolute path smuggled into a step.
    with pytest.raises(BridgeError):
        m.skill_install(
            {
                "name": "bad",
                "description": "d",
                "steps": ["read /etc/passwd now"],
            }
        )
    # Parent traversal.
    with pytest.raises(BridgeError):
        m.skill_install(
            {"name": "bad", "description": "d", "steps": ["load ../../secret"]}
        )
    # Code-style import statement.
    with pytest.raises(BridgeError):
        m.skill_install(
            {
                "name": "bad",
                "description": "d",
                "steps": ["import os"],
            }
        )
    # Oversize content.
    with pytest.raises(BridgeError):
        m.skill_install({"content": "x" * (120 * 1024)})
    # Unparseable body.
    with pytest.raises(BridgeError):
        m.skill_install({"content": "this is not a skill file"})


def test_skill_enable_unknown_name_errors(tmp_path, monkeypatch):
    import dream.tools as tools_mod

    monkeypatch.setattr(tools_mod, "WORKSPACE_ROOT", tmp_path)
    m = make_methods(tmp_path)
    with pytest.raises(BridgeError):
        m.skill_enable({"skill_id": "ghost"})
