"""Stage D — /learn pipeline and opt-in skill proposals."""

from __future__ import annotations

import json

import pytest

import cli
from dream import tools
from dream.agent import ApprovalPolicy, Dream, EchoBackend
from dream.memory import MemoryStore
from dream.skills import load_skills
from dream.skills.learn import (
    LearnError,
    classify_learn,
    install_skill_bundle,
)
from dream.skills.propose import (
    maybe_propose,
    reset_proposals_for_tests,
)
from dream.skills.store import reset_ledger_for_tests

NOTES = (
    "How to brew tea: boil fresh water, add leaves, steep five minutes."
)
LONG_CHAPTER = ("Chapter text about irrigation and soil " * 80).strip()


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setenv("DREAM_SKILLS_DB", str(tmp_path / "skills-ledger.db"))
    monkeypatch.delenv("DREAM_SKILL_PROPOSALS", raising=False)
    monkeypatch.delenv("DREAM_DEMO", raising=False)
    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)
    reset_ledger_for_tests()
    reset_proposals_for_tests()
    from dream.skills.registry import mark_skills_dirty

    mark_skills_dirty()
    return tmp_path.resolve()


@pytest.fixture()
def store(tmp_path):
    memory = MemoryStore(str(tmp_path / "dream.db"))
    yield memory
    memory.close()


class LearnBackend:
    """Follows a /learn prompt by writing one skill through edit_skill."""

    def __init__(self, name: str = "pasted-notes"):
        self.name = name
        self.prompts: list[str] = []

    def chat(self, messages, tools=None):
        del tools
        system = str(messages[0].get("content", ""))
        user = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
        if messages[-1].get("role") == "tool":
            return {"content": "saved", "tool_calls": []}
        self.prompts.append(user)
        if "Turn the following source" not in user and "save_skill" not in system:
            return {"content": f"Echo: {user}", "tool_calls": []}
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "learn-save",
                    "name": "edit_skill",
                    "arguments": {
                        "name": self.name,
                        "description": "Brew tea when the user asks how.",
                        "body": (
                            "## Purpose\n\nBrew tea.\n\n"
                            "## Instructions\n\n1. Boil water\n2. Steep leaves\n"
                        ),
                    },
                }
            ],
        }


class BundleBackend:
    def chat(self, messages, tools=None):
        del tools
        if messages[-1].get("role") == "tool":
            return {"content": "bundle saved", "tool_calls": []}
        user = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
        if "knowledge base" not in user.lower() and "references/" not in user:
            return {"content": "Echo", "tool_calls": []}
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "bundle",
                    "name": "save_skill_bundle",
                    "arguments": {
                        "name": "irrigation-notes",
                        "description": "Core models for irrigation notes.",
                        "body": (
                            "## Purpose\n\nIndex of irrigation notes.\n\n"
                            "## Instructions\n\nSee references/.\n"
                        ),
                        "references": {
                            "soil": "Distilled soil model.",
                            "water": "Distilled water model.",
                            "glossary": "canal: a water channel",
                        },
                    },
                }
            ],
        }


def _ok(payload: dict) -> dict:
    assert payload["status"] == "ok", payload
    return payload["result"]


def test_learn_from_notes(workspace, store):
    dream = Dream(store, LearnBackend("pasted-notes"))
    turn = dream.run("/learn " + NOTES)
    assert turn.tool_calls[0]["name"] == "edit_skill"
    loaded, problems = load_skills()
    assert problems == []
    assert len(loaded) == 1
    assert loaded[0].name == "pasted-notes"


def test_learn_from_path(workspace, store):
    rel = "notes/tea.txt"
    path = tools._safe_path(rel)
    path.parent.mkdir(parents=True)
    path.write_text(NOTES, encoding="utf-8")
    dream = Dream(store, LearnBackend("tea"))
    turn = dream.run("/learn notes/tea.txt")
    assert turn.tool_calls
    user = next(m["content"] for m in dream.history if m.get("role") == "user")
    assert "Source kind: path" in user
    assert "How to brew tea" in user


def test_learn_from_conversation(workspace, store):
    backend = LearnBackend("conversation-notes")
    dream = Dream(store, backend)
    dream.history.append({"role": "user", "content": NOTES})
    dream.history.append({"role": "assistant", "content": "I can help with that."})
    turn = dream.run("/learn conversation")
    assert turn.tool_calls[0]["name"] == "edit_skill"
    user = next(m["content"] for m in dream.history if "Source kind" in str(m.get("content")))
    assert "Source kind: conversation" in user


def test_learn_from_corpus_writes_references(workspace, store):
    folder = tools._safe_path("docs/book")
    folder.mkdir(parents=True)
    (folder / "soil.md").write_text(LONG_CHAPTER + " soil", encoding="utf-8")
    (folder / "water.md").write_text(LONG_CHAPTER + " water", encoding="utf-8")
    dream = Dream(store, BundleBackend())
    turn = dream.run("/learn docs/book")
    assert turn.tool_calls[0]["name"] == "save_skill_bundle"
    loaded, _ = load_skills()
    assert [s.name for s in loaded] == ["irrigation-notes"]
    refs = list((workspace / "skills" / "irrigation-notes" / "references").glob("*.md"))
    names = sorted(p.name for p in refs)
    assert "soil.md" in names
    assert "water.md" in names
    assert "glossary.md" in names
    soil = (workspace / "skills" / "irrigation-notes" / "references" / "soil.md").read_text(
        encoding="utf-8"
    )
    assert LONG_CHAPTER not in soil


def test_url_offline_refuses_bilingual(workspace, store, monkeypatch):
    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)

    def forbidden(*_a, **_k):
        raise AssertionError("network must not be touched")

    monkeypatch.setattr(tools, "_open_network_request", forbidden)
    dream = Dream(store, EchoBackend())
    turn = dream.run("/learn https://example.com/guide")
    assert turn.tool_calls == []
    text = turn.reply
    assert any("\u0600" <= c <= "\u06ff" for c in text)
    assert "network" in text.lower() or "URL" in text
    loaded, _ = load_skills()
    assert loaded == []


def test_url_with_network_enabled_uses_fetch(workspace, store, monkeypatch):
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")

    class Fake:
        def __init__(self):
            self._body = b"<html><body><p>Fetched tea guide</p></body></html>"
            self._pos = 0

        def read(self, n=-1):
            chunk = self._body[self._pos : self._pos + (len(self._body) if n < 0 else n)]
            self._pos += len(chunk)
            return chunk

        def geturl(self):
            return "https://example.com/guide"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    monkeypatch.setattr(tools, "_open_network_request", lambda *_a, **_k: Fake())
    monkeypatch.setattr(
        tools.socket,
        "getaddrinfo",
        lambda *_a, **_k: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    src = classify_learn("https://example.com/guide")
    assert src.kind == "url"
    assert "Fetched tea guide" in src.text


def test_merge_on_relearn_does_not_duplicate(workspace):
    first = install_skill_bundle(
        "tea-guide",
        "Brew tea when asked how.",
        "## Purpose\n\nFirst pass.\n",
    )
    assert first["status"] == "created"
    second = install_skill_bundle(
        "tea-guide",
        "Brew tea when asked how.",
        "## Purpose\n\nNew steeping note.\n",
    )
    assert second["status"] == "merged"
    loaded, problems = load_skills()
    assert problems == []
    assert len(loaded) == 1
    assert "First pass" in loaded[0].body
    assert "New steeping note" in loaded[0].body


def test_cli_learn_forwards_to_agent(workspace, store, capsys):
    dream = Dream(store, LearnBackend("pasted-notes"))
    assert cli.dispatch_command("/learn " + NOTES, dream, output=print)
    out = capsys.readouterr().out
    assert "saved" in out
    loaded, _ = load_skills()
    assert len(loaded) == 1


def test_proposals_default_off_and_never_in_demo(workspace, store, monkeypatch):
    monkeypatch.delenv("DREAM_SKILL_PROPOSALS", raising=False)
    long_msg = "x" * 500
    dream = Dream(store, EchoBackend())
    turn = dream.run(long_msg)
    assert "skill proposal" not in turn.reply
    demo = Dream(store, EchoBackend(), demo=True)
    monkeypatch.setenv("DREAM_SKILL_PROPOSALS", "1")
    reset_proposals_for_tests()
    turn = demo.run(long_msg)
    assert "skill proposal" not in turn.reply
    assert maybe_propose(long_msg, [{}, {}], demo=True) is None


def test_proposal_approved_applies_denied_discards(workspace, store, monkeypatch):
    monkeypatch.setenv("DREAM_SKILL_PROPOSALS", "1")
    reset_proposals_for_tests()
    long_msg = "x" * 500
    dream = Dream(store, EchoBackend())
    turn = dream.run(long_msg)
    assert "skill proposal" in turn.reply
    assert "prop-1" in turn.reply
    loaded, _ = load_skills()
    assert loaded == []

    denied = json.loads(tools.execute("discard_skill_proposal", {"proposal_id": "prop-1"}))
    assert denied["status"] == "ok"
    assert denied["result"]["discarded"] is True
    loaded, _ = load_skills()
    assert loaded == []

    reset_proposals_for_tests()
    turn = dream.run(long_msg)
    applied = _ok(json.loads(tools.execute("apply_skill_proposal", {"proposal_id": "prop-1"})))
    assert applied["applied"] is True
    loaded, _ = load_skills()
    assert len(loaded) == 1

    # Denial through approval policy leaves disk unchanged on a fresh proposal.
    reset_proposals_for_tests()
    turn = dream.run(long_msg)

    class ApplyBackend:
        def chat(self, messages, tools=None):
            del tools
            if messages[-1].get("role") == "tool":
                return {"content": "no", "tool_calls": []}
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "apply",
                        "name": "apply_skill_proposal",
                        "arguments": {"proposal_id": "prop-1"},
                    }
                ],
            }

    before = load_skills()[0]
    policy = ApprovalPolicy(
        auto_approve={"safe"},
        always_ask={"guarded", "dangerous"},
        ask=lambda n, a: False,
    )
    blocked = Dream(store, ApplyBackend(), policy)
    turn = blocked.run("apply it")
    assert turn.tool_calls[0]["allowed"] is False
    after = load_skills()[0]
    assert [s.name for s in after] == [s.name for s in before]


def test_prepare_learn_empty_notes_refuses(workspace):
    with pytest.raises(LearnError) as caught:
        classify_learn("conversation", history=[])
    text = str(caught.value)
    assert any("\u0600" <= c <= "\u06ff" for c in text)
