"""Unit and bridge tests for ``browser.*`` JSON-RPC endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods_browser import (
    browser_click,
    browser_close,
    browser_deep_crawl,
    browser_extract_content,
    browser_get_status,
    browser_launch,
    browser_navigate,
    browser_reset,
    browser_screenshot,
    browser_type_text,
)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_browser_state():
    _run(browser_reset())
    yield
    _run(browser_reset())


def test_browser_status_and_launch():
    status = _run(browser_get_status())
    assert status["status"] == "healthy"
    assert "session" in status
    assert status["session"]["is_active"] is True

    launch_res = _run(browser_launch({"backend": "mock", "headless": True}))
    assert launch_res["status"] == "launched"
    assert launch_res["session"]["backend"] == "mock"


def test_browser_navigate_and_extract():
    res = _run(browser_navigate({"url": "https://example.org/docs"}))
    assert res["status"] == "navigated"
    assert "snapshot" in res
    snapshot = res["snapshot"]
    assert snapshot["url"] == "https://example.org/docs"
    assert snapshot["status_code"] == 200
    assert len(snapshot["content_markdown"]) > 0

    extract_res = _run(browser_extract_content())
    assert extract_res["status"] == "extracted"
    assert "snapshot" in extract_res


def test_browser_interactive_actions():
    _run(browser_navigate({"url": "https://python.org"}))

    click_res = _run(browser_click({"selector": "button:has-text('Search')"}))
    assert click_res["status"] == "clicked"
    assert click_res["result"]["success"] is True

    type_res = _run(browser_type_text({"selector": "input[name='q']", "text": "asyncio"}))
    assert type_res["status"] == "typed"
    assert type_res["result"]["text"] == "asyncio"

    shot_res = _run(browser_screenshot())
    assert shot_res["status"] == "captured"
    assert "screenshot_path" in shot_res


def test_browser_deep_crawl():
    crawl_res = _run(
        browser_deep_crawl(
            {
                "url": "https://docs.python.org",
                "goal": "فهرست مستندات و کتابخانه‌ها",
                "max_depth": 2,
                "max_pages": 3,
            }
        )
    )
    assert crawl_res["status"] == "crawled"
    assert crawl_res["total_pages"] >= 1
    assert "synthesis" in crawl_res
    assert len(crawl_res["pages"]) >= 1


def test_browser_ssrf_protection():
    # Loopback IP
    with pytest.raises(BridgeError):
        _run(browser_navigate({"url": "http://127.0.0.1:8000/admin"}))

    # Localhost string
    with pytest.raises(BridgeError):
        _run(browser_navigate({"url": "http://localhost:3000"}))

    # Private IP range
    with pytest.raises(BridgeError):
        _run(browser_navigate({"url": "http://192.168.1.1/router"}))

    # Cloud metadata endpoint
    with pytest.raises(BridgeError):
        _run(browser_navigate({"url": "http://169.254.169.254/latest/meta-data/"}))


def test_browser_close_and_reset():
    close_res = _run(browser_close())
    assert close_res["status"] == "closed"

    reset_res = _run(browser_reset())
    assert reset_res["status"] == "reset"
