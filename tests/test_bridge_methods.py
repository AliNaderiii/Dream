"""Unit tests for the bridge RPC method handlers (every namespace)."""

from __future__ import annotations

import asyncio
import tempfile

import pytest

from dream.bridge.errors import APPROVAL_REQUIRED, BridgeError, invalid_params
from dream.bridge.methods import BridgeMethods, memory_to_dict
from dream.memory import MemoryStore

# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #


def make_methods() -> BridgeMethods:
    """A methods instance backed by an in-memory store and temp config paths."""
    store = MemoryStore(":memory:")
    return BridgeMethods(
        store,
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
    )


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# session.*
# --------------------------------------------------------------------------- #


def test_session_create_list_get_delete_rename():
    m = make_methods()
    created = m.session_create({"title": "First"})
    sid = created["session_id"]
    assert created["title"] == "First"

    listed = m.session_list({})
    assert listed["sessions"][0]["id"] == sid

    got = m.session_get({"session_id": sid})
    assert got["title"] == "First"

    renamed = m.session_rename({"session_id": sid, "title": "Renamed"})
    assert renamed["title"] == "Renamed"

    deleted = m.session_delete({"session_id": sid})
    assert deleted == {"deleted": True, "session_id": sid}
    assert m.session_list({})["sessions"] == []


def test_session_requires_valid_id():
    m = make_methods()
    with pytest.raises(BridgeError) as exc:
        m.session_get({"session_id": "missing"})
    assert exc.value.code == invalid_params("").code
    with pytest.raises(BridgeError):
        m.session_get({})
    with pytest.raises(BridgeError):
        m.session_rename({"session_id": None, "title": "x"})


# --------------------------------------------------------------------------- #
# conversation.*
# --------------------------------------------------------------------------- #


def test_conversation_send_streams_and_returns_turn():
    m = make_methods()
    sid = m.session_create({})["session_id"]

    stream = run(m.conversation_send({"session_id": sid, "message": "hello world"}))
    chunks = run(_collect(stream.chunks))

    assert "".join(c["token"] for c in chunks) == stream.final["reply"]
    assert stream.final["reply"] == "Echo: hello world"
    assert stream.final["tool_calls"] == []
    # message count and timestamps updated
    assert m.session_get({"session_id": sid})["message_count"] == 1


def test_conversation_send_math_turn_uses_tool():
    m = make_methods()
    sid = m.session_create({})["session_id"]
    stream = run(m.conversation_send({"session_id": sid, "message": "What is 12 * 3?"}))
    assert stream.final["tool_calls"], "echo backend should emit a calculate tool call"
    assert stream.final["tool_calls"][0]["name"] == "calculate"


def test_conversation_send_rejects_empty_message():
    m = make_methods()
    sid = m.session_create({})["session_id"]
    with pytest.raises(BridgeError) as exc:
        run(m.conversation_send({"session_id": sid, "message": "   "}))
    assert exc.value.code == -32602


def test_conversation_stop_sets_event():
    m = make_methods()
    sid = m.session_create({})["session_id"]
    out = run(m.conversation_stop({"session_id": sid}))
    assert out["stopped"] is True


async def _collect(aiter):
    return [item async for item in aiter]


# --------------------------------------------------------------------------- #
# provider.*
# --------------------------------------------------------------------------- #


def test_provider_list_includes_echo_default():
    m = make_methods()
    out = m.provider_list({})
    assert out["default"] == "echo"
    kinds = {p["kind"] for p in out["providers"]}
    assert "echo" in kinds or out["providers"] == []  # empty until configured is fine


def test_provider_configure_then_list_and_default():
    m = make_methods()
    saved = m.provider_configure(
        {
            "id": "my-ollama",
            "provider": {"kind": "ollama", "model": "llama3.2"},
            "set_default": True,
        }
    )
    assert saved["default"] == "my-ollama"
    listed = m.provider_list({})
    assert any(p["id"] == "my-ollama" for p in listed["providers"])


def test_provider_configure_rejects_unknown_kind():
    m = make_methods()
    with pytest.raises(BridgeError):
        m.provider_configure({"provider": {"kind": "magic"}})


def test_provider_test_echo_is_ok():
    m = make_methods()
    out = run(m.provider_test({"provider": "echo"}))
    assert out["ok"] is True
    assert out["latency_ms"] == 0


# --------------------------------------------------------------------------- #
# memory.*
# --------------------------------------------------------------------------- #


def _seed(m):
    mem = m.store.remember("I like dark coffee", kind="semantic", tags=["coffee"])
    return mem.id


def test_memory_list_search_get_update_delete():
    m = make_methods()
    mid = _seed(m)

    listed = m.memory_list({})
    assert any(mem["id"] == mid for mem in listed["memories"])

    searched = m.memory_search({"query": "coffee"})
    assert searched["memories"]
    assert searched["memories"][0]["content"] == "I like dark coffee"

    got = m.memory_get({"memory_id": mid})
    assert got["id"] == mid

    updated = m.memory_update({"memory_id": mid, "content": "I like tea", "importance": 0.9})
    assert updated["memory"]["content"] == "I like tea"
    assert updated["memory"]["importance"] == 0.9

    deleted = m.memory_delete({"memory_id": mid})
    assert deleted["deleted"] is True
    assert m.memory_get({"memory_id": mid}) is None


def test_memory_get_missing_returns_none():
    m = make_methods()
    assert m.memory_get({"memory_id": 999999}) is None


def test_memory_update_rejects_bad_kind_and_importance():
    m = make_methods()
    mid = _seed(m)
    with pytest.raises(BridgeError):
        m.memory_update({"memory_id": mid, "kind": "bogus"})
    with pytest.raises(BridgeError):
        m.memory_update({"memory_id": mid, "importance": 5.0})


def test_memory_to_dict_round_trip():
    m = make_methods()
    mid = _seed(m)
    d = memory_to_dict(m.store.get(mid))
    assert set(d) == {
        "id", "kind", "content", "tags", "importance", "created_at",
        "last_used_at", "use_count", "source", "archived", "pinned", "score",
    }


# --------------------------------------------------------------------------- #
# skill.*
# --------------------------------------------------------------------------- #


def test_skill_install_get_list_remove(tmp_path, monkeypatch):
    # Skills are written under tools.WORKSPACE_ROOT; point it at a temp dir for
    # the duration of this test (no module reload — that would reset REGISTRY).
    import dream.tools as tools_mod

    monkeypatch.setattr(tools_mod, "WORKSPACE_ROOT", tmp_path)

    m = make_methods()
    installed = m.skill_install(
        {"name": "brewing", "description": "how to brew coffee", "steps": ["grind", "pour"]}
    )
    assert installed["status"] == "installed"

    listed = m.skill_list({})
    names = [s["name"] for s in listed["skills"]]
    assert "brewing" in names

    found = m.skill_get({"query": "brew coffee"})
    assert found["match"]["name"] == "brewing"

    removed = m.skill_remove({"name": "brewing"})
    assert removed["removed"] is True
    assert m.skill_get({"query": "brew"})["match"] is None


def test_skill_install_validates_params():
    m = make_methods()
    with pytest.raises(BridgeError):
        m.skill_install({"name": "", "description": "x", "steps": ["a"]})
    with pytest.raises(BridgeError):
        m.skill_install({"name": "x", "description": "", "steps": ["a"]})
    with pytest.raises(BridgeError):
        m.skill_install({"name": "x", "description": "y", "steps": []})


# --------------------------------------------------------------------------- #
# tool.*
# --------------------------------------------------------------------------- #


def test_tool_list_exposes_registry():
    m = make_methods()
    out = m.tool_list({})
    names = {t["name"] for t in out["tools"]}
    assert "calculate" in names
    assert all("risk" in t and "schema" in t for t in out["tools"])


def test_tool_execute_runs_safe_tool():
    m = make_methods()
    out = m.tool_execute({"name": "calculate", "arguments": {"expression": "2 + 3"}})
    assert out["status"] == "ok"
    assert out["result"] == 5


def test_tool_execute_unknown_tool_invalid_params():
    m = make_methods()
    with pytest.raises(BridgeError):
        m.tool_execute({"name": "no_such_tool", "arguments": {}})


def test_tool_execute_dangerous_requires_approval():
    m = make_methods()
    with pytest.raises(BridgeError) as exc:
        m.tool_execute({"name": "run_shell", "arguments": {"command": "echo hi"}})
    assert exc.value.code == APPROVAL_REQUIRED
    approval_id = exc.value.data["approval_id"]
    assert approval_id


def test_tool_execute_dangerous_with_approved_flag_runs():
    # run_shell is dangerous; with approved=True it executes (echo is harmless).
    m = make_methods()
    out = m.tool_execute(
        {"name": "run_shell", "arguments": {"command": "echo bridge"}, "approved": True}
    )
    assert out["status"] == "ok"
    assert "bridge" in out["result"]["stdout"]


# --------------------------------------------------------------------------- #
# approval.*
# --------------------------------------------------------------------------- #


def test_approval_request_then_resolve_allowed_executes():
    m = make_methods()
    req = m.approval_request({"name": "run_shell", "arguments": {"command": "echo ok"}})
    aid = req["approval_id"]
    assert req["risk"] == "dangerous"

    resolved = m.approval_resolve({"approval_id": aid, "allowed": True})
    assert resolved["status"] == "ok"
    assert "ok" in resolved["result"]["stdout"]


def test_approval_resolve_denied_returns_blocked():
    m = make_methods()
    req = m.approval_request({"name": "run_shell", "arguments": {"command": "rm -rf /"}})
    aid = req["approval_id"]
    out = m.approval_resolve({"approval_id": aid, "allowed": False})
    assert out["blocked"] is True


def test_approval_resolve_twice_rejected():
    m = make_methods()
    req = m.approval_request({"name": "run_shell", "arguments": {"command": "echo x"}})
    aid = req["approval_id"]
    m.approval_resolve({"approval_id": aid, "allowed": False})
    with pytest.raises(BridgeError):
        m.approval_resolve({"approval_id": aid, "allowed": True})


# --------------------------------------------------------------------------- #
# subagent.*
# --------------------------------------------------------------------------- #


def test_subagent_spawn_completes_and_lists():
    """A child runs to completion inside the sidecar's event loop.

    Every call shares one ``asyncio.run``: subagents live in tasks on the
    loop that spawned them, which in production is the sidecar's single
    long-lived loop.
    """
    m = make_methods()

    async def scenario():
        spawned = await m.subagent_spawn({"message": "hello"})
        sid = spawned["subagent_id"]
        assert spawned["status"] in {"idle", "running"}
        status = await _wait_for_terminal(m, sid)
        listed = m.subagent_list({})
        return sid, status, listed

    sid, status, listed = run(scenario())
    assert status["status"] == "completed", status
    assert status["result"] == "Echo: hello"
    assert any(s["id"] == sid for s in listed["subagents"])


def test_subagent_cancel_marks_cancelled():
    m = make_methods()

    async def scenario():
        spawned = await m.subagent_spawn({"message": "hello"})
        return await m.subagent_cancel({"subagent_id": spawned["subagent_id"]})

    out = run(scenario())
    assert out["cancelled"] is True
    assert out["status"] in {"cancelled", "completed"}


async def _wait_for_terminal(m, sub_id, tries=200):
    for _ in range(tries):
        s = m.subagent_status({"subagent_id": sub_id})
        if s["status"] not in {"idle", "running"}:
            return s
        await asyncio.sleep(0.01)
    return m.subagent_status({"subagent_id": sub_id})


# --------------------------------------------------------------------------- #
# health / version / serialisation
# --------------------------------------------------------------------------- #


def test_health_check_and_version():
    m = make_methods()
    health = m.health_check({})
    assert health["status"] == "ok"
    assert health["sessions"] == 0

    version = m.sidecar_version({})
    assert version["protocol"] == "1.0"
    assert version["core"]
    assert version["python"]


def test_turn_to_dict_has_documented_fields():
    m = make_methods()
    sid = m.session_create({})["session_id"]
    stream = run(m.conversation_send({"session_id": sid, "message": "hi"}))
    d = stream.final
    for key in (
        "reply", "tool_calls", "memories_used", "memories_created",
        "memories_superseded", "memories_merged", "elapsed_seconds",
        "extraction", "memory_errors",
    ):
        assert key in d


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
