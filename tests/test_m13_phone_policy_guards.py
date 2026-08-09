"""Pins M13's three small riders on the M12 phone/terminal seam.

What this pins and what evidence justified it:

- Rider one (dispatch bar): M12 gave search a permissive bar and left
  dispatch strict, but nothing pinned which bar the use_skill *tool* uses —
  forcing the tool to the permissive flag kept the whole suite green at 567.
  This test spies on the matcher through the tool boundary and asserts the
  strict default is what the tool actually passes.

- Rider two (refused phone set): the M12 test for the six reviewed commands
  asserts only that a decision exists and its reason is longer than ten
  characters, so flipping /dedupe from refused to allowed stayed green (9
  passed). These tests lock the refused set itself and the phone behaviour
  of a refused command.

- Rider three (stats path leak): /stats returns the absolute database path
  in its JSON. Measured: the phone reply contained ``"path":
  "/tmp/.../m.db"``. The phone must not show a filesystem path; the
  terminal owner may see his own. These tests pin the phone reply without
  the path and the terminal reply with it.

Break-and-restore evidence: each test was observed red against a deliberate
one-line break (permissive flag in the tool, /dedupe flipped to allowed,
phone stats strip removed) and green again after the break was reverted
(messages in the PR).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import cli
from dream import skills as skills_module
from dream import tools as dream_tools
from dream.agent import Dream
from dream.memory import MemoryStore
from dream.telegram import TelegramBot

OWNER = 4242

# Gloss: بیمه
BIME_QUERY = "\u0628\u06cc\u0645\u0647"


def _fake_token() -> str:
    return "123456789:" + "A_b-c" * 7


def _update(update_id: int, chat_id: int, text: str, *, user_id: int | None = None):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id if user_id is None else user_id},
            "text": text,
        },
    }


class FakeTransport:
    def __init__(self):
        self.sent: list[tuple[int, str, float]] = []

    def get_updates(self, *, offset, allowed_updates, poll_timeout, http_timeout):
        return []

    def send_message(self, *, chat_id, text, http_timeout):
        self.sent.append((chat_id, text, http_timeout))

    def send_chat_action(self, *, chat_id, action, http_timeout):
        pass


def _make_bot(store: MemoryStore, transport: FakeTransport) -> TelegramBot:
    return TelegramBot(
        _fake_token(),
        store,
        transport=transport,
        allowed_user=OWNER,
        backend_factory=lambda: SimpleNamespace(
            run=lambda msg: SimpleNamespace(reply="dummy")
        ),
        output=lambda x: None,
    )


# ---------------------------------------------------------------------------
# Rider one: the use_skill tool must keep the strict dispatch bar
# ---------------------------------------------------------------------------


def test_use_skill_tool_keeps_the_strict_dispatch_bar(monkeypatch):
    """The matcher function is pinned strict by M12; this pins which bar the
    tool actually passes when a real turn executes it."""
    seen: list[bool] = []

    def spy(query, *, permissive=False):
        seen.append(permissive)
        return None

    monkeypatch.setattr(skills_module, "find_skill", spy)
    result = dream_tools.execute("use_skill", {"query": BIME_QUERY})
    assert json.loads(result)["status"] == "ok"
    assert seen == [False], (
        f"use_skill must dispatch with the strict bar; the tool passed "
        f"permissive={seen}"
    )


# ---------------------------------------------------------------------------
# Rider two: the refused phone set is locked
# ---------------------------------------------------------------------------


def test_phone_refused_set_is_locked():
    """A refused command must stay refused: /dedupe and /pin are bulk
    destructive or maintenance commands the phone must never open. The M12
    test only checked that a decision exists; this locks the decision."""
    from cli import _PHONE_POLICY, _PHONE_REFUSED_CANONICAL  # type: ignore

    assert _PHONE_REFUSED_CANONICAL == frozenset({"/dedupe", "/pin", "/exit"}), (
        f"refused set changed: {sorted(_PHONE_REFUSED_CANONICAL)}"
    )
    for cmd in _PHONE_REFUSED_CANONICAL:
        allowed, reason = _PHONE_POLICY[cmd]
        assert allowed is False, f"{cmd} must stay refused"
        assert isinstance(reason, str) and len(reason.strip()) > 10


def test_phone_refuses_a_locked_command_in_behaviour(tmp_path):
    """Sending /dedupe on the phone must produce the refusal line, never the
    dedupe dry-run output — behaviour, not just the policy table."""
    db = str(tmp_path / "dedupe.db")
    transport = FakeTransport()
    with MemoryStore(db) as store:
        store.remember("coffee", kind="semantic", importance=0.5)
        bot = _make_bot(store, transport)
        bot.process_updates([_update(1, OWNER, "/dedupe")])
        assert transport.sent
        reply = transport.sent[-1][1]
        assert reply == "This command is not available in Telegram. Type /help.", (
            f"locked command must be refused, got: {reply!r}"
        )


# ---------------------------------------------------------------------------
# Rider three: the phone /stats reply carries no filesystem path
# ---------------------------------------------------------------------------


def _run_phone_stats(store: MemoryStore, transport: FakeTransport) -> str:
    bot = _make_bot(store, transport)
    bot.process_updates([_update(1, OWNER, "/stats")])
    assert transport.sent, "phone should have replied"
    return transport.sent[-1][1]


def test_phone_stats_reply_hides_the_filesystem_path(tmp_path):
    db = str(tmp_path / "stats.db")
    transport = FakeTransport()
    with MemoryStore(db) as store:
        store.remember("coffee", kind="semantic", importance=0.5)
        reply = _run_phone_stats(store, transport)
        assert '"total"' in reply
        assert "path" not in reply, f"phone stats must not leak a path: {reply!r}"
        assert str(tmp_path) not in reply
        assert db not in reply


def test_terminal_stats_keeps_the_filesystem_path(tmp_path):
    """The terminal reply is unchanged: the owner reading his own terminal
    may see his own database path."""
    db = str(tmp_path / "terminal.db")
    with MemoryStore(db) as store:
        dream = Dream(store)
        lines: list[str] = []
        cli.dispatch_command("/stats", dream, lines.append)
        terminal_reply = "\n".join(lines)
        assert '"path"' in terminal_reply
        assert db in terminal_reply
