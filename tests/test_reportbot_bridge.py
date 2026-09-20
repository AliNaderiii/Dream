"""Tests for the ``reportbot.*`` bridge methods (start/stop/status).

The handlers are resolved at test runtime through ``importlib`` — the
extension-seam tests evict every ``dream.bridge.methods_*`` module from
``sys.modules``, so collection-time imports would go stale.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from dream.bridge.errors import BridgeError
from dream.reporting.telegram_bot import ReportBotError

VALID_TOKEN = "123456789:AAFakeDreamBotTokenForTests_-abc123XYZ"


class FakeService:
    def __init__(self) -> None:
        self.started: list[tuple[str, str | None]] = []
        self.stop_calls = 0
        self.fail_start: str | None = None

    def start(self, token: str, api_base_url: str | None = None) -> dict:
        if self.fail_start:
            raise ReportBotError(self.fail_start)
        self.started.append((token, api_base_url))
        return {"running": True, "events": [{"kind": "started"}]}

    def stop(self) -> dict:
        self.stop_calls += 1
        return {"running": False, "events": []}

    def status(self) -> dict:
        return {"running": bool(self.started) and not self.stop_calls, "events": []}


@pytest.fixture()
def service(monkeypatch: pytest.MonkeyPatch) -> FakeService:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    fake = FakeService()
    monkeypatch.setattr(module, "get_report_bot_service", lambda: fake)
    yield fake
    # Defensive teardown: never leave a real poller thread behind.
    bot_module = importlib.import_module("dream.reporting.telegram_bot")
    bot_module.reset_report_bot_service()


def run(coro):
    return asyncio.run(coro)


def test_handlers_registered() -> None:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    assert set(module.HANDLERS) == {"reportbot.start", "reportbot.stop", "reportbot.status"}


def test_start_requires_a_token_string(service: FakeService) -> None:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    for bad in (None, 123, "", "   "):
        with pytest.raises(BridgeError):
            run(module.reportbot_start({"token": bad}))


def test_start_rejects_overlong_token(service: FakeService) -> None:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    with pytest.raises(BridgeError, match="at most 256"):
        run(module.reportbot_start({"token": "x" * 257}))
    assert service.started == []


def test_start_passes_token_and_optional_base_url(service: FakeService) -> None:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    result = run(
        module.reportbot_start({"token": VALID_TOKEN, "api_base_url": "https://relay.example/"})
    )
    assert result["success"] is True
    assert result["running"] is True
    assert service.started == [(VALID_TOKEN, "https://relay.example/")]


def test_start_maps_service_error_to_invalid_params(service: FakeService) -> None:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    service.fail_start = "a report bot is already running; stop it first"
    with pytest.raises(BridgeError, match="already running"):
        run(module.reportbot_start({"token": VALID_TOKEN}))


def test_stop_returns_success(service: FakeService) -> None:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    result = run(module.reportbot_stop({}))
    assert result["success"] is True
    assert service.stop_calls == 1


def test_status_passthrough(service: FakeService) -> None:
    module = importlib.import_module("dream.bridge.methods_reportbot")
    result = run(module.reportbot_status(None))
    assert result == {"running": False, "events": []}
