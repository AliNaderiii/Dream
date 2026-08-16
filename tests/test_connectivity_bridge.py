"""gateway.* RPC methods on the bridge (P-07, §3.11 of the protocol)."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore


@pytest.fixture()
def methods(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_CONNECTIVITY_PATH", str(tmp_path / "connectivity.json"))
    store = MemoryStore(":memory:")
    methods = BridgeMethods(
        store,
        sessions_path=str(tmp_path / "sessions.json"),
        providers_path=str(tmp_path / "providers.json"),
        default_provider="echo",
    )
    yield methods
    asyncio.run(methods.aclose())


def test_gateway_platforms_lists_all_six_with_public_config(methods):
    result = methods.gateway_platforms({})
    names = [platform["name"] for platform in result["platforms"]]
    assert names == ["telegram", "discord", "slack", "whatsapp", "signal", "email"]
    telegram = result["platforms"][0]
    assert telegram["privacy"] == "plaintext"
    assert telegram["max_message_length"] == 4096
    assert any(field["key"] == "token" for field in telegram["fields"])
    signal = result["platforms"][4]
    assert signal["privacy"] == "e2e"


def test_gateway_configure_status_and_redaction(methods):
    result = asyncio.run(
        methods.gateway_configure(
            {
                "platform": "telegram",
                "config": {"token": "123456:ABCDEFG", "enabled": True, "note": "hi"},
            }
        )
    )
    assert result["saved"] is True
    assert result["config"]["token"] == "••••••••"
    assert result["config"]["note"] == "hi"
    assert result["config"]["configured"] is True
    # The secret really is stored (locally), but status never reveals it.
    platforms = methods.gateway_platforms({})["platforms"]
    telegram = next(p for p in platforms if p["name"] == "telegram")
    assert telegram["enabled"] is True
    assert telegram["configured"] is True
    status = methods.gateway_status({})
    assert status["running"] is True


def test_gateway_start_stop_leave_unconfigured_adapters_dormant(methods):
    started = asyncio.run(methods.gateway_start({}))
    # Nothing is enabled/configured, so every adapter stays down and no
    # network I/O happens.
    assert all(row["running"] is False for row in started["adapters"])
    stopped = asyncio.run(methods.gateway_stop({}))
    assert all(row["running"] is False for row in stopped["adapters"])


def test_gateway_link_users_and_unlink(methods):
    code = methods.gateway_link_code({"platform": "telegram"})
    assert len(code["code"]) == 6
    assert code["platform"] == "telegram"
    assert code["expires_at"] > code["issued_at"]
    # Same platform returns the same pending code rather than burning codes.
    again = methods.gateway_link_code({"platform": "telegram"})
    assert again["code"] == code["code"]

    assert methods.gateway_linked_users({}) == {"linked_users": []}
    removed = methods.gateway_unlink_user({"platform": "telegram", "user_id": "42"})
    assert removed["unlinked"] is False


def test_gateway_logs_and_param_validation(methods):
    assert methods.gateway_logs({}) == {"platform": None, "entries": [], "total": 0}
    assert methods.gateway_logs({"platform": "signal", "limit": 10})["entries"] == []
    with pytest.raises(BridgeError):
        asyncio.run(methods.gateway_configure({"platform": "carrier-pigeon", "config": {}}))
    with pytest.raises(BridgeError):
        methods.gateway_link_code({})
    with pytest.raises(BridgeError):
        methods.gateway_unlink_user({"platform": "telegram"})
    with pytest.raises(BridgeError):
        methods.gateway_logs({"limit": "lots"})


def test_aclose_stops_the_gateway_loop(methods):
    gateway = methods._ensure_gateway()
    assert gateway.is_running
    asyncio.run(methods.aclose())
    assert gateway.is_running is False
    methods._gateway = None  # let the fixture's teardown aclose() be a no-op
