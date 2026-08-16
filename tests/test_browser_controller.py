"""Tests for dream.browser_controller — Chrome browser control module.

These tests verify the module structure and error handling without requiring
a real Chrome browser or Playwright installation.
"""

from __future__ import annotations

import pytest


def test_browser_controller_import():
    """Verify the module imports cleanly."""
    from dream.browser_controller import (
        BrowserController,
        BrowserSecurityError,
        BrowserTimeoutError,
        BrowserUnavailableError,
    )

    assert BrowserController is not None
    assert BrowserUnavailableError is not None
    assert issubclass(BrowserUnavailableError, RuntimeError)
    assert BrowserTimeoutError is not None
    assert issubclass(BrowserTimeoutError, RuntimeError)
    assert BrowserSecurityError is not None
    assert issubclass(BrowserSecurityError, RuntimeError)


def test_browser_controller_init():
    """Creating a BrowserController does not raise."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    assert bc is not None
    assert bc._screenshot_dir is not None
    assert bc._approved_domains == set()


def test_page_content_defaults():
    """PageContent has sensible defaults."""
    from dream.browser_controller import PageContent

    pc = PageContent()
    assert pc.url == ""
    assert pc.title == ""
    assert pc.text == ""
    assert pc.html == ""
    assert pc.links == []
    assert pc.tables == []
    assert pc.screenshot_path is None


def test_browser_session_defaults():
    """BrowserSession has sensible defaults."""
    from dream.browser_controller import BrowserSession

    bs = BrowserSession(
        id="test", url="https://example.com", purpose="Testing", domain="example.com"
    )
    assert bs.id == "test"
    assert bs.url == "https://example.com"
    assert bs.purpose == "Testing"
    assert bs.domain == "example.com"
    assert bs.status == "pending"
    assert bs.allowed_once is False
    assert bs.always_allow_domain is False
    assert bs.created_at > 0
    assert bs.started_at is None
    assert bs.closed_at is None


def test_request_approval_creates_pending_session():
    """request_approval creates a pending session."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    session = bc.request_approval("https://example.com", "Test")
    assert session.status == "pending"
    assert session.url == "https://example.com"
    assert session.domain == "example.com"
    assert session.id in bc._pending_approvals


def test_approve_session_activates_pending():
    """approve_session activates a pending session."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    session = bc.request_approval("https://example.com", "Test")
    updated = bc.approve_session(session.id)
    assert updated is not None
    assert updated.status == "active"
    assert updated.allowed_once is True


def test_approve_session_always_allow_adds_domain():
    """approve_session with always_allow=True adds domain to approved set."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id, always_allow=True)
    assert "example.com" in bc._approved_domains


def test_deny_session_closes_pending():
    """deny_session closes a pending session."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    session = bc.request_approval("https://example.com", "Test")
    updated = bc.deny_session(session.id)
    assert updated is not None
    assert updated.status == "closed"
    assert updated.closed_at is not None


def test_approve_unknown_session_returns_none():
    """approve_session for unknown session id returns None."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    assert bc.approve_session("nonexistent") is None


def test_deny_unknown_session_returns_none():
    """deny_session for unknown session id returns None."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    assert bc.deny_session("nonexistent") is None


def test_get_status_returns_dict():
    """get_status returns a dict with expected keys."""
    from dream.browser_controller import BrowserController

    bc = BrowserController()
    status = bc.get_status()
    assert isinstance(status, dict)
    assert "attached" in status
    assert "attached_to_existing" in status
    assert "pending_approvals" in status
    assert "approved_domains" in status
    assert "current_session" in status


def test_attach_existing_browser_raises_without_chrome():
    """attach_existing_browser raises BrowserUnavailableError when no Chrome."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.attach_existing_browser(port=9999))


def test_launch_isolated_raises_without_chrome():
    """launch_isolated_browser raises BrowserUnavailableError when no Chrome."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.launch_isolated_browser())


def test_navigate_raises_without_browser():
    """navigate raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.navigate("https://example.com"))


def test_get_content_raises_without_browser():
    """get_content raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.get_content())


def test_execute_js_raises_without_browser():
    """execute_js raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.execute_js("1+1"))


def test_fill_form_raises_without_browser():
    """fill_form raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.fill_form("#input", "test"))


def test_click_raises_without_browser():
    """click raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.click("#button"))


def test_screenshot_raises_without_browser():
    """screenshot raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.screenshot())


def test_get_cookies_raises_without_browser():
    """get_cookies raises BrowserUnavailableError when no context."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    import asyncio
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.get_cookies())


def test_browser_unavailable_error_message():
    """BrowserUnavailableError has a meaningful message."""
    from dream.browser_controller import BrowserUnavailableError

    err = BrowserUnavailableError("Chrome not found")
    assert str(err) == "Chrome not found"


def test_browser_security_error_message():
    """BrowserSecurityError has a meaningful message."""
    from dream.browser_controller import BrowserSecurityError

    err = BrowserSecurityError("URL not approved")
    assert str(err) == "URL not approved"


def test_bridge_reflects_browser_imports():
    """The bridge re-exports browser types when available."""
    try:
        from dream.bridge import BrowserController, BrowserSession, PageContent

        assert BrowserController is not None
        assert BrowserSession is not None
        assert PageContent is not None
    except ImportError:
        pass  # OK if playwright not installed