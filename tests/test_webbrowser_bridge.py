"""Honesty tests for the ``webbrowser.*`` bridge (real browser controller).

The controller itself is faked (no playwright, no Chrome): the contract under
test is honest availability, strict validation, and the approval-gated
navigation mapping — never a fake page.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any

import pytest

from dream.bridge import methods_webbrowser as mt
from dream.bridge.errors import BridgeError
from dream.browser_controller import BrowserSecurityError


def run(handler, **params):
    return asyncio.run(handler(params))


@dataclasses.dataclass
class FakeContent:
    url: str = "https://example.com/page"
    title: str = "Example"
    text: str = "hello"
    html: str = "<p>hello</p>"
    links: list = dataclasses.field(default_factory=lambda: [{"text": "docs", "href": "/docs"}])
    tables: list = dataclasses.field(default_factory=list)
    screenshot_path: str | None = None


@dataclasses.dataclass
class FakeSession:
    id: str = "browser-abc123"
    url: str = "https://example.com"
    purpose: str = "تست"
    domain: str = "example.com"
    status: str = "pending"
    allowed_once: bool = False
    approved_at: float | None = None
    created_at: float = 0.0
    started_at: float | None = None
    closed_at: float | None = None
    fetch_count: int = 0


class FakeController:
    def __init__(self) -> None:
        self.approved: list[str] = []
        self.denied: list[str] = []

    def get_status(self) -> dict[str, Any]:
        return {
            "attached": True,
            "has_page": True,
            "session_fetch_count": 3,
            "max_fetches": 20,
            "current_session": {"id": "browser-abc123", "domain": "example.com"},
        }

    async def navigate(self, url: str, purpose: str = "", timeout: int = 30) -> FakeContent:
        if url == "https://need-approval.example":
            raise BrowserSecurityError(
                "Navigation requires user approval.", reason="approval_required"
            )
        if url == "https://blocked.example":
            raise BrowserSecurityError("blocked", reason="blocklist")
        return FakeContent()  # type: ignore[return-value]

    def request_approval(self, url: str, purpose: str) -> FakeSession:
        return FakeSession()

    def approve_session(self, session_id: str) -> FakeSession | None:
        self.approved.append(session_id)
        s = FakeSession()
        s.status = "active"
        return s

    def deny_session(self, session_id: str) -> FakeSession | None:
        self.denied.append(session_id)
        return None if session_id == "missing" else FakeSession()

    async def click(self, selector: str) -> None:
        if selector == "bad":
            raise RuntimeError("selector not found")

    async def fill_form(self, selector: str, value: str) -> None:
        pass

    async def screenshot(self, path: str | None = None) -> Any:
        return "/tmp/shot.png"

    async def close(self) -> None:
        pass


@pytest.fixture()
def fake(monkeypatch):
    ctrl = FakeController()
    monkeypatch.setattr(mt, "_playwright_available", lambda: True)
    monkeypatch.setattr(mt, "_controller", lambda: ctrl)
    return ctrl


def test_status_honest_without_playwright(monkeypatch):
    monkeypatch.setattr(mt, "_playwright_available", lambda: False)
    res = run(mt.HANDLERS["webbrowser.status"])
    assert res["available"] is False
    assert "pip install" in res["error"]


def test_status_reports_real_controller(fake):
    res = run(mt.HANDLERS["webbrowser.status"])
    assert res["available"] is True
    assert res["controller"]["session_fetch_count"] == 3


@pytest.mark.parametrize(
    "params",
    [
        {"port": 0},
        {"port": 70000},
        {"port": "9222"},
    ],
)
def test_attach_validates_port(params):
    with pytest.raises(BridgeError):
        run(mt.HANDLERS["webbrowser.attach"], **params)


@pytest.mark.parametrize(
    "params",
    [
        {"url": ""},
        {"url": "   "},
        {"timeout": 2},
        {"timeout": 500},
        {"timeout": "30"},
    ],
)
def test_navigate_validates(params):
    with pytest.raises(BridgeError):
        run(mt.HANDLERS["webbrowser.navigate"], **({"url": "https://x.example"} | params))


def test_navigate_maps_approval_required(fake):
    res = run(
        mt.HANDLERS["webbrowser.navigate"], url="https://need-approval.example"
    )
    assert res["success"] is False
    assert res["status"] == "approval_required"
    assert res["session"]["domain"] == "example.com"


def test_navigate_maps_security_reason(fake):
    res = run(mt.HANDLERS["webbrowser.navigate"], url="https://blocked.example")
    assert res["success"] is False
    assert res["reason"] == "blocklist"
    assert "status" not in res


def test_navigate_success_returns_content(fake):
    res = run(mt.HANDLERS["webbrowser.navigate"], url="https://example.com/page")
    assert res["success"] is True
    assert res["content"]["title"] == "Example"
    assert res["content"]["links"] == [{"text": "docs", "href": "/docs"}]


def test_request_returns_pending_session(fake):
    res = run(mt.HANDLERS["webbrowser.request"], url="https://example.com", purpose="خواندن")
    assert res["success"] is True
    assert res["session"]["status"] == "pending"


def test_approve_and_deny_route_to_controller(fake):
    res = run(mt.HANDLERS["webbrowser.approve"], session_id="browser-abc123")
    assert res["success"] is True and res["session"]["status"] == "active"
    assert fake.approved == ["browser-abc123"]
    res = run(mt.HANDLERS["webbrowser.deny"], session_id="browser-abc123")
    assert res["success"] is True
    assert fake.denied == ["browser-abc123"]
    res = run(mt.HANDLERS["webbrowser.deny"], session_id="missing")
    assert res["success"] is False


def test_click_reports_selector_miss(fake):
    res = run(mt.HANDLERS["webbrowser.click"], selector="bad")
    assert res["success"] is False
    assert "selector not found" in res["error"]


def test_screenshot_returns_path(fake):
    res = run(mt.HANDLERS["webbrowser.screenshot"])
    assert res["success"] is True and res["screenshot_path"] == "/tmp/shot.png"


def test_handlers_registered():
    assert set(mt.HANDLERS) == {
        "webbrowser.status",
        "webbrowser.attach",
        "webbrowser.launch",
        "webbrowser.request",
        "webbrowser.approve",
        "webbrowser.deny",
        "webbrowser.navigate",
        "webbrowser.content",
        "webbrowser.click",
        "webbrowser.fill",
        "webbrowser.screenshot",
        "webbrowser.close",
    }
