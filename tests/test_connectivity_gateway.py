"""Gateway tests: adapter lifecycle, routing pipeline, auth, sessions, log.

Uses a fake adapter and a fake Dream factory so the whole pipeline
(auth → rate limit → command → session → split → reply → log) runs with no
network and no model backend.
"""

from __future__ import annotations

import tempfile
from types import SimpleNamespace
from typing import Any

from dream.connectivity.base import PlatformAdapter
from dream.connectivity.config import REDACTED_VALUE, ConnectivityConfig
from dream.connectivity.gateway import (
    LINK_BAD_TEXT,
    LINK_OK_TEXT,
    RATE_LIMITED_TEXT,
    REFUSAL_TEXT,
    Gateway,
)
from dream.connectivity.models import IncomingMessage


class FakeDream:
    """A deterministic stand-in for dream.agent.Dream."""

    instances = 0

    def __init__(self) -> None:
        FakeDream.instances += 1

    def run(self, message: str) -> Any:
        return SimpleNamespace(reply=f"reply to: {message}")


class FakeAdapter(PlatformAdapter):
    """A test adapter exercising the whole PlatformAdapter contract."""

    platform_name = "fake"
    max_message_length = 500
    supports_inline = True
    supports_attachments = False
    privacy = "plaintext"

    def __init__(self, config: dict[str, Any], *, on_message) -> None:
        super().__init__(config, on_message=on_message)
        self.sent: list[tuple[str, str]] = []
        self.typing_calls = 0
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1
        self._status.running = True
        self._status.connected = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self._status.running = False
        self._status.connected = False

    async def send_message(self, user_id: str, text: str, attachments: list | None = None) -> None:
        self.sent.append((user_id, text))

    async def send_typing_indicator(self, user_id: str) -> None:
        self.typing_calls += 1


class SecretAdapter(FakeAdapter):
    """An end-to-end-encrypted stand-in (Signal semantics)."""

    platform_name = "secret"
    privacy = "e2e"


def _tmp_paths() -> dict[str, str]:
    directory = tempfile.mkdtemp()
    return {
        "config": f"{directory}/connectivity.json",
        "sessions": f"{directory}/sessions.json",
        "links": f"{directory}/links.json",
        "log": f"{directory}/log.jsonl",
    }


def _make_gateway(
    adapter: PlatformAdapter | None = None,
) -> tuple[Gateway, ConnectivityConfig, FakeAdapter]:
    paths = _tmp_paths()
    config = ConnectivityConfig(paths["config"])
    config.set(adapter.platform_name if adapter else "fake", {"enabled": True})
    gateway = Gateway(
        config,
        sessions_path=paths["sessions"],
        links_path=paths["links"],
        log_path=paths["log"],
        dream_factory=FakeDream,
    )
    gateway.register_adapter(adapter or FakeAdapter({}, on_message=gateway._on_adapter_message))
    gateway.start_loop()
    return gateway, config, gateway.adapter(adapter.platform_name if adapter else "fake")


def _message(platform: str, user_id: str, text: str) -> IncomingMessage:
    return IncomingMessage(
        platform=platform,
        platform_user_id=user_id,
        platform_channel_id=user_id,
        text=text,
        message_id=f"m-{text[:6]}",
    )


def _send(gateway: Gateway, message: IncomingMessage) -> None:
    gateway.submit(gateway.route_message(message))


# --------------------------------------------------------------------------- #
# G2 — adapter lifecycle
# --------------------------------------------------------------------------- #


def test_adapters_register_start_and_stop_through_the_gateway():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        assert gateway.is_running
        status = gateway.submit(gateway.start_all())
        assert status["running"] is True
        assert adapter.start_calls == 1
        row = gateway.adapter_status("fake")
        assert row["running"] is True

        gateway.submit(gateway.stop_all())
        assert adapter.stop_calls == 1
        assert gateway.adapter_status("fake")["running"] is False
    finally:
        gateway.stop_loop()
    assert gateway.is_running is False


def test_unconfigured_adapters_are_skipped_at_start():
    paths = _tmp_paths()
    config = ConnectivityConfig(paths["config"])
    config.set("telegram", {"enabled": True})  # no token → not configured
    gateway = Gateway(
        config,
        sessions_path=paths["sessions"],
        links_path=paths["links"],
        log_path=paths["log"],
        dream_factory=FakeDream,
    )
    gateway.register_default_adapters()
    gateway.start_loop()
    try:
        status = gateway.submit(gateway.start_all())
        telegram = next(a for a in status["adapters"] if a["platform"] == "telegram")
        assert telegram["running"] is False
        assert telegram["detail"] == "missing configuration"
    finally:
        gateway.stop_loop()


# --------------------------------------------------------------------------- #
# G4 — the routing pipeline
# --------------------------------------------------------------------------- #


def test_unlinked_user_is_refused_and_link_flow_grants_access():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        gateway.submit(gateway.start_all())
        # Unlinked: everything except /link and /help is refused.
        _send(gateway, _message("fake", "u1", "hello"))
        assert adapter.sent[-1] == ("u1", REFUSAL_TEXT)

        # /link with a bad code is handled (still refused afterwards).
        _send(gateway, _message("fake", "u1", "/link 000000"))
        assert adapter.sent[-1] == ("u1", LINK_BAD_TEXT)
        _send(gateway, _message("fake", "u1", "hello"))
        assert adapter.sent[-1] == ("u1", REFUSAL_TEXT)

        # Issue a code, redeem it, get linked.
        code = gateway.link_code("fake")
        assert code["platform"] == "fake"
        assert len(code["code"]) == 6
        _send(gateway, _message("fake", "u1", f"/link {code['code']}"))
        assert adapter.sent[-1] == ("u1", LINK_OK_TEXT)
        assert gateway.linked_users("fake")[0]["user_id"] == "u1"

        # Now the message reaches the agent.
        _send(gateway, _message("fake", "u1", "hello"))
        assert adapter.sent[-1] == ("u1", "reply to: hello")

        # The code was single-use.
        _send(gateway, _message("fake", "u2", f"/link {code['code']}"))
        assert adapter.sent[-1] == ("u2", LINK_BAD_TEXT)
    finally:
        gateway.stop_loop()


def test_commands_and_agent_replies_follow_the_pipeline():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        gateway.submit(gateway.start_all())
        config.set("fake", {"enabled": True, "require_auth": False})
        _send(gateway, _message("fake", "u1", "plain message"))
        assert adapter.sent[-1] == ("u1", "reply to: plain message")
        assert adapter.typing_calls == 1  # typing indicator before the turn

        _send(gateway, _message("fake", "u1", "/help"))
        assert "commands" in adapter.sent[-1][1]

        _send(gateway, _message("fake", "u1", "/status"))
        assert "session messages: 1" in adapter.sent[-1][1]

        _send(gateway, _message("fake", "u1", "/new_session"))
        assert adapter.sent[-1][1] == "New session started. History forgotten."
        _send(gateway, _message("fake", "u1", "/status"))
        assert "session messages: 0" in adapter.sent[-1][1]

        # Non-command text still reaches the agent after the session reset.
        _send(gateway, _message("fake", "u1", "another"))
        assert adapter.sent[-1] == ("u1", "reply to: another")
    finally:
        gateway.stop_loop()


def test_rate_limit_is_enforced_per_platform_and_user():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        gateway.submit(gateway.start_all())
        config.set("fake", {"enabled": True, "require_auth": False})
        gateway.configure("fake", {"rate_limit_per_minute": 1})
        _send(gateway, _message("fake", "u1", "first"))
        assert adapter.sent[-1] == ("u1", "reply to: first")
        _send(gateway, _message("fake", "u1", "second"))
        assert adapter.sent[-1] == ("u1", RATE_LIMITED_TEXT)
        # Another user is unaffected.
        _send(gateway, _message("fake", "u2", "second"))
        assert adapter.sent[-1] == ("u2", "reply to: second")
    finally:
        gateway.stop_loop()


def test_long_replies_are_split_to_the_adapter_limit():
    FakeDream.instances = 0

    class LongReplyDream(FakeDream):
        def run(self, message: str) -> Any:
            return SimpleNamespace(reply=("abcdefghijklmnopqrstuvwxyz " * 10).strip())

    class SmallAdapter(FakeAdapter):
        """50-char transport so the splitter is forced to work."""

        platform_name = "small"
        max_message_length = 50

    paths = _tmp_paths()
    config = ConnectivityConfig(paths["config"])
    config.set("small", {"enabled": True, "require_auth": False})
    gateway = Gateway(
        config,
        sessions_path=paths["sessions"],
        links_path=paths["links"],
        log_path=paths["log"],
        dream_factory=LongReplyDream,
    )
    adapter = SmallAdapter({}, on_message=gateway._on_adapter_message)
    gateway.register_adapter(adapter)
    gateway.start_loop()
    try:
        gateway.submit(gateway.start_all())
        _send(gateway, _message("small", "u1", "make it long"))
        replies = [text for user_id, text in adapter.sent if user_id == "u1"]
        expected = ("abcdefghijklmnopqrstuvwxyz " * 10).strip()
        assert len(replies) > 1
        # The splitter absorbs the boundary space; rejoining with a space
        # reconstructs the original text exactly.
        assert " ".join(replies) == expected
        assert all(len(chunk) <= 50 for chunk in replies)
    finally:
        gateway.stop_loop()


# --------------------------------------------------------------------------- #
# G5 — sessions persist per channel
# --------------------------------------------------------------------------- #


def test_second_message_reuses_the_same_dream_instance():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        gateway.submit(gateway.start_all())
        config.set("fake", {"enabled": True, "require_auth": False})
        _send(gateway, _message("fake", "u1", "one"))
        _send(gateway, _message("fake", "u1", "two"))
        _send(gateway, _message("fake", "u2", "three"))
        assert FakeDream.instances == 2  # u1 reused; u2 created fresh
        stats = gateway.submit(gateway.stop_all)
        del stats
    finally:
        gateway.stop_loop()


# --------------------------------------------------------------------------- #
# G6 — message log
# --------------------------------------------------------------------------- #


def test_message_log_records_inbound_and_outbound_and_persists():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        gateway.submit(gateway.start_all())
        config.set("fake", {"enabled": True, "require_auth": False})
        _send(gateway, _message("fake", "u1", "inbound text"))
        entries = gateway.logs("fake")["entries"]
        directions = [entry["direction"] for entry in entries]
        assert directions == ["out", "in"]  # newest first
        assert entries[0]["text"] == "reply to: inbound text"
        assert entries[1]["text"] == "inbound text"
        assert entries[1]["user_id"] == "u1"
        assert gateway.status()["messages"] == {"inbound": 1, "outbound": 1}
    finally:
        gateway.stop_loop()


def test_e2e_platform_log_entries_never_store_content():
    FakeDream.instances = 0
    paths = _tmp_paths()
    config = ConnectivityConfig(paths["config"])
    config.set("secret", {"enabled": True})
    gateway = Gateway(
        config,
        sessions_path=paths["sessions"],
        links_path=paths["links"],
        log_path=paths["log"],
        dream_factory=FakeDream,
    )
    gateway.register_adapter(
        SecretAdapter({}, on_message=gateway._on_adapter_message)
    )
    gateway.start_loop()
    try:
        gateway.submit(gateway.start_all())
        config.set("secret", {"enabled": True, "require_auth": False})
        _send(gateway, _message("secret", "u1", "very private message"))
        entries = gateway.logs("secret")["entries"]
        assert entries, "e2e traffic must still be logged (without content)"
        assert all(entry["text"] == "" for entry in entries)
    finally:
        gateway.stop_loop()


# --------------------------------------------------------------------------- #
# configure / redaction / unlink
# --------------------------------------------------------------------------- #


def test_configure_redacts_secrets_and_unlink_revokes_access():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        gateway.submit(gateway.start_all())
        redacted = gateway.configure(
            "telegram", {"token": "123456:ABCDEF", "note": "visible", "enabled": True}
        )
        assert redacted["token"] == REDACTED_VALUE
        assert redacted["note"] == "visible"
        # The stored config really holds the secret; public views do not.
        assert config.get("telegram")["token"] == "123456:ABCDEF"
        assert config.public("telegram")["token"] == REDACTED_VALUE
        assert config.configured("telegram") is True

        linked = gateway.linked_users()
        assert linked == []
        _send(gateway, _message("fake", "u1", "/link 123456"))
        assert gateway.linked_users("fake") == []
        result = gateway.unlink_user("fake", "u1")
        assert result["unlinked"] is False
    finally:
        gateway.stop_loop()


def test_status_aggregates_adapters_and_counters():
    FakeDream.instances = 0
    gateway, config, adapter = _make_gateway()
    try:
        gateway.submit(gateway.start_all())
        status = gateway.status()
        assert status["running"] is True
        assert [row["platform"] for row in status["adapters"]] == ["fake"]
        assert status["rate_limit"]["default"] == 20
    finally:
        gateway.stop_loop()
