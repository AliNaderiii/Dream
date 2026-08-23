"""Bridge error paths for the MEM families (MEM Stage F).

Every wire boundary of the ``memory2.*``, ``search.sessions.*``,
``conversation.compact`` / ``nudge.status`` and ``skills.*`` families is
pinned here: malformed params fail as ``invalid_params``, domain refusals
carry the kernel's bilingual message, a refusal changes nothing, and every
family payload is JSON-serialisable end to end (the ``slots=True`` dataclass
regression). Stores live under a per-test tmp workspace so nothing touches
``data/``.
"""

from __future__ import annotations

import json

import pytest

from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore
from dream.memory_stores import EntryNotFoundError, StoreCapacityError
from dream.session_search import SessionIndexError
from dream.skills import propose as propose_module
from dream.skills.propose import SkillProposal
from dream.skills.store import SkillLedger
from dream.tools import WORKSPACE_ROOT as _REAL_WORKSPACE_ROOT


def make_methods(tmp_path, monkeypatch) -> BridgeMethods:
    """A hermetic BridgeMethods: every store and the workspace in tmp."""
    monkeypatch.setenv("DREAM_BOUNDED_DB", str(tmp_path / "bounded.db"))
    monkeypatch.setenv("DREAM_SESSION_INDEX_DB", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("DREAM_SKILLS_DB", str(tmp_path / "skills.db"))
    monkeypatch.delenv("DREAM_SKILL_PROPOSALS", raising=False)
    monkeypatch.delenv("DREAM_DEMO", raising=False)
    import dream.tools as tools_module

    monkeypatch.setattr(tools_module, "WORKSPACE_ROOT", tmp_path)
    propose_module.reset_proposals_for_tests()
    return BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=str(tmp_path / "sessions.json"),
        providers_path=str(tmp_path / "providers.json"),
        disabled_skills_path=str(tmp_path / "disabled.json"),
        default_provider="echo",
    )


def message_of(call) -> str:
    """Assert an invalid-params refusal and return its message."""
    with pytest.raises(BridgeError) as caught:
        call()
    assert caught.value.code == INVALID_PARAMS
    return str(caught.value)


@pytest.fixture(autouse=True)
def restore_workspace_root():
    """Nothing leaks the real workspace, even when a test forgets to tidy."""
    yield
    import dream.tools as tools_module

    tools_module.WORKSPACE_ROOT = _REAL_WORKSPACE_ROOT


def write_skill_md(tmp_path, folder: str) -> None:
    root = tmp_path / "skills" / folder
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        "---\n"
        f"name: {folder}\n"
        "description: A demo v2 skill used by the references listing.\n"
        "---\n\n"
        "## Purpose\n\nDemo body so the parser accepts the file.\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# memory2.*
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "params",
    [{}, {"target": None}, {"target": ""}, {"target": "agent"}, {"target": 42}],
    ids=["absent", "none", "blank", "unknown-name", "non-string"],
)
def test_memory2_unknown_target_is_invalid_params(tmp_path, monkeypatch, params):
    m = make_methods(tmp_path, monkeypatch)
    merged = {"text": "one fact", **params}
    assert "target must be" in message_of(lambda: m.memory2_add(merged))


@pytest.mark.parametrize(
    "payload",
    [None, 42, [], {}, True],
    ids=["none", "int", "list", "dict", "bool"],
)
def test_memory2_non_string_payload_is_invalid_params(tmp_path, monkeypatch, payload):
    m = make_methods(tmp_path, monkeypatch)
    assert "text must be a string" in message_of(
        lambda: m.memory2_add({"target": "memory", "text": payload})
    )


def test_memory2_snapshot_returns_both_targets_with_the_five_wire_keys(
    tmp_path, monkeypatch
):
    import re

    m = make_methods(tmp_path, monkeypatch)
    out = m.memory2_snapshot({})
    assert set(out) == {"memory", "user"}
    for target, store in out.items():
        assert set(store) == {"target", "header", "used_chars", "capacity", "entries"}
        assert store["target"] == target
        assert re.match(r"^\[\d+% — [\d,]+/[\d,]+ chars\]$", store["header"])


def test_memory2_remove_of_a_missing_entry_leaves_the_store_untouched(
    tmp_path, monkeypatch
):
    m = make_methods(tmp_path, monkeypatch)
    before = m.memory2_snapshot({"target": "user"})
    with pytest.raises(EntryNotFoundError):
        m.memory2_remove({"target": "user", "old": "not there"})
    assert m.memory2_snapshot({"target": "user"}) == before


@pytest.mark.parametrize("mode", ["add", "replace"])
def test_memory2_overflow_refusal_leaves_the_store_untouched(
    tmp_path, monkeypatch, mode
):
    m = make_methods(tmp_path, monkeypatch)
    if mode == "add":
        m.memory2_add({"target": "memory", "text": "x" * 2100})
        with pytest.raises(StoreCapacityError):
            m.memory2_add({"target": "memory", "text": "y" * 200})
    else:
        m.memory2_add({"target": "memory", "text": "a" * 1000})
        m.memory2_add({"target": "memory", "text": "b" * 1000})
        with pytest.raises(StoreCapacityError):
            m.memory2_replace(
                {"target": "memory", "old": "a" * 50, "new": "z" * 1500}
            )
    assert m.memory2_snapshot({"target": "memory"})["used_chars"] <= 2200


def test_memory2_status_mirrors_the_live_snapshot(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    m.memory2_add({"target": "memory", "text": "fresh fact"})
    assert m.memory2_status({}) == m.memory2_snapshot({})


# --------------------------------------------------------------------------- #
# conversation.compact / nudge.status
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "method_name", ["conversation.compact", "nudge.status"],
)
@pytest.mark.parametrize(
    "params",
    [{}, {"session_id": 42}, {"session_id": "sess_missing"}],
    ids=["missing", "non-string", "unknown"],
)
def test_compact_and_nudge_require_a_known_session(
    tmp_path, monkeypatch, method_name, params
):
    m = make_methods(tmp_path, monkeypatch)
    handler = getattr(m, method_name.replace(".", "_"))
    assert "known session_id is required" in message_of(lambda: handler(params))


def test_nudge_status_returns_exactly_enabled_sent_due_all_bools(
    tmp_path, monkeypatch
):
    m = make_methods(tmp_path, monkeypatch)
    session_id = m.session_create({})["session_id"]
    out = m.nudge_status({"session_id": session_id})
    assert set(out) == {"enabled", "sent", "due"}
    assert all(isinstance(value, bool) for value in out.values())


# --------------------------------------------------------------------------- #
# search.sessions.*
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "query", [None, 42, [], {}], ids=["none", "int", "list", "dict"]
)
def test_search_sessions_query_requires_a_string_query(
    tmp_path, monkeypatch, query
):
    m = make_methods(tmp_path, monkeypatch)
    assert "query must be a string" in message_of(
        lambda: m.search_sessions_query({"query": query})
    )


def test_search_sessions_query_with_no_tokens_fails_closed(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    with pytest.raises(SessionIndexError) as caught:
        m.search_sessions_query({"query": "!!!"})
    assert "no searchable tokens" in str(caught.value)


def test_search_sessions_status_and_snippet_rules_shape(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    status = m.search_sessions_status({})
    assert set(status) == {"healthy", "documents"}
    assert status["healthy"] is True
    assert isinstance(status["documents"], int)
    rules = m.search_sessions_snippet_rules({})
    assert set(rules) == {"normalized", "highlight", "max_width_chars"}
    assert rules["max_width_chars"] == 110


def test_search_sessions_rebuild_returns_the_document_count(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    m.session_index.index_session("sess-1", "Runbook", ["rolled out the bridge"])
    assert m.search_sessions_rebuild({}) == {"rebuilt": 1}


# --------------------------------------------------------------------------- #
# skills.* boundary errors
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "params", [{}, {"name": "   "}, {"name": 42}],
    ids=["missing", "blank", "non-string"],
)
def test_skills_versions_requires_a_real_name(tmp_path, monkeypatch, params):
    m = make_methods(tmp_path, monkeypatch)
    assert "name must be a non-empty string" in message_of(
        lambda: m.skills_versions(params)
    )


def test_skills_use_log_rejects_a_non_string_name(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    assert "name must be a string" in message_of(
        lambda: m.skills_use_log({"name": 42})
    )


def test_skills_propose_requires_a_message(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    assert "message must be a non-empty string" in message_of(
        lambda: m.skills_propose({})
    )
    assert "message must be a non-empty string" in message_of(
        lambda: m.skills_propose({"message": "   "})
    )


def test_skills_apply_proposal_requires_a_string_id(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    assert "proposal_id must be a string" in message_of(
        lambda: m.skills_apply_proposal({"proposal_id": 42})
    )


def _seed_applied_proposal(m: BridgeMethods) -> str:
    """Enable proposals, create one, approve it; return its resolved id."""
    import os

    os.environ["DREAM_SKILL_PROPOSALS"] = "1"
    propose_module.reset_proposals_for_tests()
    created = m.skills_propose({"message": "word " * 120})["proposal"]
    assert created is not None
    assert m.skills_apply_proposal({"proposal_id": created["proposal_id"]})[
        "applied"
    ] is True
    return created["proposal_id"]


@pytest.mark.parametrize("mode", ["never-known", "already-applied"])
def test_skills_apply_proposal_refuses_unknown_or_resolved_ids(
    tmp_path, monkeypatch, mode
):
    m = make_methods(tmp_path, monkeypatch)
    proposal_id = "prop-never"
    if mode == "already-applied":
        proposal_id = _seed_applied_proposal(m)
    assert "unknown or already resolved proposal" in message_of(
        lambda: m.skills_apply_proposal({"proposal_id": proposal_id})
    )


def test_skills_discard_proposal_is_false_for_a_never_pending_proposal(
    tmp_path, monkeypatch
):
    m = make_methods(tmp_path, monkeypatch)
    assert m.skills_discard_proposal({"proposal_id": "prop-none"}) == {
        "discarded": False
    }


def test_skills_proposals_lists_pending_reviews_oldest_first(
    tmp_path, monkeypatch
):
    m = make_methods(tmp_path, monkeypatch)
    propose_module._PENDING["prop-new"] = SkillProposal(
        "prop-new", "new-topic", "new", "body", "create", 20.0
    )
    propose_module._PENDING["prop-old"] = SkillProposal(
        "prop-old", "old-topic", "old", "body", "improve", 10.0
    )
    out = m.skills_proposals({})
    assert [item["proposal_id"] for item in out["proposals"]] == [
        "prop-old",
        "prop-new",
    ]
    assert set(out["proposals"][0]) == {
        "proposal_id",
        "name",
        "description",
        "body",
        "action",
        "created_at",
    }


# --------------------------------------------------------------------------- #
# skills.learn_classify
# --------------------------------------------------------------------------- #


def test_skills_learn_classify_requires_a_string_argument(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    assert "argument must be a string" in message_of(
        lambda: m.skills_learn_classify({"argument": 42})
    )


def test_skills_learn_classify_requires_a_list_history(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    assert "history must be a list" in message_of(
        lambda: m.skills_learn_classify(
            {"argument": "notes", "history": {"role": "user"}}
        )
    )


def test_skills_learn_classifies_pasted_notes(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    out = m.skills_learn_classify({"argument": "dream deployment runbook notes"})
    source = out["source"]
    assert source["kind"] == "notes"
    assert source["topic"]
    assert source["text"].startswith("dream deployment")
    assert source["existing"] is None


def test_skills_learn_classifies_the_conversation(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    out = m.skills_learn_classify(
        {
            "argument": "conversation",
            "history": [
                {"role": "user", "content": "we shipped the bridge today"},
                {"role": "assistant", "content": "noted and filed"},
            ],
        }
    )
    assert out["source"]["kind"] == "conversation"
    assert "we shipped the bridge today" in out["source"]["text"]


def test_skills_learn_classify_refuses_an_empty_conversation(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    with pytest.raises(BridgeError) as caught:
        m.skills_learn_classify({"argument": "conversation", "history": []})
    assert caught.value.code == INVALID_PARAMS
    assert "could not be read" in str(caught.value)
    assert caught.value.data == {"kind": "conversation"}


def test_skills_learn_classify_refuses_a_url_while_the_network_is_off(
    tmp_path, monkeypatch
):
    import dream.skills.learn as learn_module

    m = make_methods(tmp_path, monkeypatch)
    monkeypatch.setattr(learn_module, "_network_on", lambda: False)
    with pytest.raises(BridgeError) as caught:
        m.skills_learn_classify({"argument": "https://example.com/runbook"})
    assert caught.value.code == INVALID_PARAMS
    # Gloss: \u0627\u06cc\u0646\u062a\u0631\u0646\u062a (internet) — the bilingual refusal.
    assert "\u0627\u06cc\u0646\u062a\u0631\u0646\u062a" in str(caught.value)
    assert caught.value.data == {"kind": "url"}


# --------------------------------------------------------------------------- #
# skills.references
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("params", [{}, {"name": ""}], ids=["missing", "blank"])
def test_skills_references_requires_a_name(tmp_path, monkeypatch, params):
    m = make_methods(tmp_path, monkeypatch)
    assert "name must be a non-empty string" in message_of(
        lambda: m.skills_references(params)
    )


def test_skills_references_names_an_unknown_skill(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    assert "unknown skill" in message_of(
        lambda: m.skills_references({"name": "ghost-skill"})
    )


@pytest.mark.parametrize(
    "kind", ["legacy-file", "v2-folder-without-dir", "v2-folder-with-empty-dir"]
)
def test_skills_references_reports_an_empty_list_without_references(
    tmp_path, monkeypatch, kind
):
    m = make_methods(tmp_path, monkeypatch)
    if kind == "legacy-file":
        skills = tmp_path / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "legacy-demo.txt").write_text(
            "name: legacy demo\n"
            "description: A legacy single-file skill.\n"
            "steps:\n- one\n- two\n",
            encoding="utf-8",
        )
        name = "legacy demo"
    elif kind == "v2-folder-without-dir":
        write_skill_md(tmp_path, "folder-demo")
        name = "folder-demo"
    else:
        write_skill_md(tmp_path, "empty-demo")
        (tmp_path / "skills" / "empty-demo" / "references").mkdir()
        name = "empty-demo"
    out = m.skills_references({"name": name})
    assert out["references"] == []


# --------------------------------------------------------------------------- #
# The wire-shape regression: every family payload is JSON-serialisable.
# --------------------------------------------------------------------------- #


def test_every_mem_family_payload_is_json_serialisable(tmp_path, monkeypatch):
    m = make_methods(tmp_path, monkeypatch)
    monkeypatch.setenv("DREAM_SKILL_PROPOSALS", "1")
    propose_module.reset_proposals_for_tests()

    # Non-empty rows for every list-bearing family, exactly as the wire sees them.
    with SkillLedger(str(tmp_path / "skills.db")) as ledger:
        ledger.record_version("demo-skill", "## Purpose\n\nDemo.\n", kind="skill_md")
        ledger.log_use("demo-skill", "ok", source="seed")
    m.session_index.index_session(
        "sess-1", "Deployment runbook", ["rolled out the bridge"], source="seed"
    )
    write_skill_md(tmp_path, "demo-skill")
    (tmp_path / "skills" / "demo-skill" / "references").mkdir()
    (tmp_path / "skills" / "demo-skill" / "references" / "glossary.md").write_text(
        "# Glossary\n", encoding="utf-8"
    )
    proposal = m.skills_propose({"message": "word " * 120})["proposal"]
    assert proposal is not None
    session_id = m.session_create({})["session_id"]

    payloads = {
        "memory2.snapshot": m.memory2_snapshot({}),
        "memory2.add": m.memory2_add({"target": "memory", "text": "fact"}),
        "memory2.status": m.memory2_status({}),
        "search.sessions.query": m.search_sessions_query({"query": "bridge"}),
        "search.sessions.status": m.search_sessions_status({}),
        "search.sessions.rebuild": m.search_sessions_rebuild({}),
        "skills.versions": m.skills_versions({"name": "demo-skill"}),
        "skills.use_log": m.skills_use_log(None),
        "skills.propose": {"proposal": proposal},
        "skills.proposals": m.skills_proposals({}),
        "skills.learn_status": m.skills_learn_status({}),
        "skills.learn_classify": m.skills_learn_classify(
            {"argument": "conversation", "history": [{"role": "user", "content": "x"}]}
        ),
        "skills.references": m.skills_references({"name": "demo-skill"}),
        "conversation.compact": m.conversation_compact({"session_id": session_id}),
        "nudge.status": m.nudge_status({"session_id": session_id}),
    }
    for name, payload in payloads.items():
        assert json.dumps(payload), name
    hits = payloads["search.sessions.query"]["results"]
    assert hits and set(hits[0]) == {
        "session_id",
        "title",
        "snippet",
        "score",
        "matched_in_title",
        "updated_at",
        "source",
    }
    versions = payloads["skills.versions"]["versions"]
    assert versions and versions[0]["kind"] == "skill_md"
    references = payloads["skills.references"]["references"]
    assert references and references[0]["name"] == "glossary"
    assert references[0]["bytes"] > 0
