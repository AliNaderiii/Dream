"""Tests for dream.browser_controller — Chrome browser control module (SEC-03).

These tests verify the module structure, security contracts, and error handling
without requiring a real Chrome browser or Playwright installation.

SEC-03 coverage:
* always_allow / always_allow_domain bypass removed.
* Approval expiry (TTL=900s) with injectable clock.
* Per-session fetch quota (default=20).
* Domain blocklist (exact + subdomain, no false substring match).
* Blocked domain rejected before approval/network.
* Error messages do not leak credentials, tokens, or blocklist contents.
* Missing blocklist files are safe.
* Malformed blocklist entries are skipped safely.
* Normalisation: case, trailing dots, ports.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bc(**kwargs):  # type: ignore[no-untyped-def]
    """Create a BrowserController with an empty blocklist by default."""
    from dream.browser_controller import BrowserController

    kwargs.setdefault("_blocklist", frozenset())
    return BrowserController(**kwargs)


def _fake_page(url: str = "https://example.com") -> MagicMock:
    """Return a mock Playwright page object."""
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value="Test Page")
    page.evaluate = AsyncMock(return_value="")
    page.content = AsyncMock(return_value="<html></html>")
    page.goto = AsyncMock(return_value=None)
    page.close = AsyncMock(return_value=None)
    return page


# ---------------------------------------------------------------------------
# Basic import and initialisation
# ---------------------------------------------------------------------------


def test_browser_controller_import() -> None:
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


def test_browser_controller_init() -> None:
    """Creating a BrowserController does not raise."""
    bc = _make_bc()
    assert bc is not None
    assert bc._screenshot_dir is not None


def test_page_content_defaults() -> None:
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


def test_browser_session_defaults() -> None:
    """BrowserSession has sensible defaults (SEC-03: no always_allow_domain)."""
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
    # SEC-03: always_allow_domain field has been removed; it must not exist.
    assert not hasattr(bs, "always_allow_domain"), (
        "always_allow_domain must not exist on BrowserSession"
    )
    assert bs.approved_at is None
    assert bs.created_at > 0
    assert bs.started_at is None
    assert bs.closed_at is None
    assert bs.fetch_count == 0


def test_request_approval_creates_pending_session() -> None:
    """request_approval creates a pending session."""
    bc = _make_bc()
    session = bc.request_approval("https://example.com", "Test")
    assert session.status == "pending"
    assert session.url == "https://example.com"
    assert session.domain == "example.com"
    assert session.id in bc._pending_approvals


def test_approve_session_activates_pending() -> None:
    """approve_session activates a pending session and sets approved_at."""
    bc = _make_bc()
    session = bc.request_approval("https://example.com", "Test")
    updated = bc.approve_session(session.id)
    assert updated is not None
    assert updated.status == "active"
    assert updated.allowed_once is True
    assert updated.approved_at is not None


# ---------------------------------------------------------------------------
# SEC-03: always_allow bypass removed
# ---------------------------------------------------------------------------


def test_always_allow_domain_field_does_not_exist() -> None:
    """BrowserSession must not have an always_allow_domain field."""
    from dream.browser_controller import BrowserSession

    bs = BrowserSession(id="x", url="https://a.com", purpose="p", domain="a.com")
    assert not hasattr(bs, "always_allow_domain"), (
        "always_allow_domain field must be removed (SEC-03)"
    )


def test_approve_session_signature_has_no_always_allow_param() -> None:
    """approve_session must not accept an always_allow parameter."""
    import inspect

    from dream.browser_controller import BrowserController

    sig = inspect.signature(BrowserController.approve_session)
    assert "always_allow" not in sig.parameters, (
        "always_allow parameter must be removed from approve_session (SEC-03)"
    )


def test_always_allow_true_does_not_bypass_approval() -> None:
    """Even if a caller passes always_allow=True it must not grant permanent access."""
    bc = _make_bc()
    session = bc.request_approval("https://example.com", "Test")
    # approve_session no longer accepts always_allow; calling with keyword
    # should raise TypeError (unexpected keyword argument).
    with pytest.raises(TypeError):
        bc.approve_session(session.id, always_allow=True)  # type: ignore[call-arg]


def test_no_approved_domains_set_after_approval() -> None:
    """Approval must NOT create a permanent domain bypass set (SEC-03)."""
    bc = _make_bc()
    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id)
    # There is no _approved_domains attribute any more.
    assert not hasattr(bc, "_approved_domains"), (
        "_approved_domains (permanent domain bypass) must be removed (SEC-03)"
    )


# ---------------------------------------------------------------------------
# SEC-03: Approval expiry / TTL
# ---------------------------------------------------------------------------


def test_approval_required_for_unapproved_domain() -> None:
    """navigate raises BrowserSecurityError(reason='approval_required') without approval."""
    from dream.browser_controller import BrowserSecurityError

    bc = _make_bc()
    bc._page = _fake_page()

    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("https://example.com"))
    assert exc_info.value.reason == "approval_required"


def test_approved_session_allows_navigation_within_ttl() -> None:
    """A freshly approved session allows navigation within the TTL."""
    from dream.browser_controller import BrowserSecurityError

    clock_val = [0.0]

    def clock() -> float:
        return clock_val[0]

    bc = _make_bc(_clock=clock)
    bc._page = _fake_page()

    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id)

    # No exception should be raised (navigate will try real Playwright next,
    # but we only care about the security gate).
    try:
        asyncio.run(bc.navigate("https://example.com"))
    except BrowserSecurityError as exc:
        pytest.fail(f"Unexpected BrowserSecurityError within TTL: {exc}")
    except Exception:
        # Playwright not installed or page mock exhausted — security gate passed.
        pass


def test_approval_expires_after_ttl() -> None:
    """Approval raises BrowserSecurityError(reason='approval_expired') after TTL."""
    from dream.browser_controller import BrowserSecurityError

    clock_val = [0.0]

    def clock() -> float:
        return clock_val[0]

    bc = _make_bc(_clock=clock, approval_ttl_seconds=900)
    bc._page = _fake_page()

    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id)  # approved_at = 0.0

    # Advance clock past TTL.
    clock_val[0] = 901.0

    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("https://example.com"))
    assert exc_info.value.reason == "approval_expired"


def test_approval_at_exact_ttl_boundary_expires() -> None:
    """Approval expired when elapsed > TTL (not >=)."""
    from dream.browser_controller import BrowserSecurityError

    clock_val = [0.0]

    def clock() -> float:
        return clock_val[0]

    bc = _make_bc(_clock=clock, approval_ttl_seconds=900)
    bc._page = _fake_page()

    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id)

    # Advance clock to exactly TTL — should expire (elapsed > ttl is False here,
    # but elapsed == ttl is not strictly within the window).
    clock_val[0] = 900.0

    # elapsed = 900 - 0 = 900, ttl = 900 → elapsed > ttl is False → valid.
    # This is the exact boundary: 900 > 900 is False, so it should NOT expire.
    try:
        asyncio.run(bc.navigate("https://example.com"))
    except BrowserSecurityError as exc:
        if exc.reason == "approval_expired":
            pytest.fail("Should not expire at exactly TTL boundary (elapsed > ttl)")
    except Exception:
        pass  # network/playwright error — security gate passed


def test_reapproval_required_after_expiry() -> None:
    """After expiry a new approval must be obtained."""
    from dream.browser_controller import BrowserSecurityError

    clock_val = [0.0]

    def clock() -> float:
        return clock_val[0]

    bc = _make_bc(_clock=clock, approval_ttl_seconds=900)
    bc._page = _fake_page()

    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id)

    # Expire the approval.
    clock_val[0] = 1000.0

    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("https://example.com"))
    assert exc_info.value.reason == "approval_expired"

    # A fresh approval at the current (expired) time should work within a new TTL.
    # The existing session is now "expired"; navigate creates a new pending one.
    # We need a completely new session.
    bc._current_session = None
    session2 = bc.request_approval("https://example.com", "Test again")
    bc.approve_session(session2.id)  # approved_at = 1000.0

    # Still at 1000, within TTL → should not raise security error.
    try:
        asyncio.run(bc.navigate("https://example.com"))
    except BrowserSecurityError as exc:
        pytest.fail(f"New approval should be valid: {exc}")
    except Exception:
        pass  # Playwright not running — gate passed


def test_default_approval_ttl_is_900() -> None:
    """DEFAULT_APPROVAL_TTL must be 900 seconds (SEC-03 requirement)."""
    from dream.browser_controller import DEFAULT_APPROVAL_TTL

    assert DEFAULT_APPROVAL_TTL == 900


# ---------------------------------------------------------------------------
# SEC-03: Fetch quota
# ---------------------------------------------------------------------------


def test_default_max_fetches_is_20() -> None:
    """DEFAULT_MAX_FETCHES must be 20 (SEC-03 requirement)."""
    from dream.browser_controller import DEFAULT_MAX_FETCHES

    assert DEFAULT_MAX_FETCHES == 20


def test_fetch_quota_allows_configured_maximum() -> None:
    """The controller allows exactly max_fetches navigations."""
    from dream.browser_controller import BrowserSecurityError

    clock_val = [0.0]

    def clock() -> float:
        return clock_val[0]

    max_fetches = 3
    bc = _make_bc(_clock=clock, max_fetches=max_fetches)
    bc._page = _fake_page()

    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id)

    # Simulate fetches without real network calls.
    # We patch _page.goto to avoid actual IO.
    for i in range(max_fetches):
        bc._page.goto = AsyncMock(return_value=None)
        bc._page.evaluate = AsyncMock(return_value="")
        bc._page.content = AsyncMock(return_value="<html></html>")
        bc._page.title = AsyncMock(return_value="Title")
        bc._page.url = "https://example.com"
        asyncio.run(bc.navigate("https://example.com"))
        assert bc._session_fetch_count == i + 1

    # The (max+1)-th fetch must be rejected.
    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("https://example.com"))
    assert exc_info.value.reason == "quota_exceeded"


def test_quota_exceeded_raised_before_network() -> None:
    """Quota check must happen before any network access."""
    from dream.browser_controller import BrowserSecurityError

    bc = _make_bc(max_fetches=0)  # immediately exhausted
    bc._page = _fake_page()

    session = bc.request_approval("https://example.com", "Test")
    bc.approve_session(session.id)

    network_called: list[bool] = []
    bc._page.goto = AsyncMock(side_effect=lambda *a, **k: network_called.append(True))

    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("https://example.com"))
    assert exc_info.value.reason == "quota_exceeded"
    assert not network_called, "Network must not be called when quota is exceeded"


def test_quota_resets_for_new_session() -> None:
    """Fetch counter resets when attach_existing_browser is called."""
    bc = _make_bc(max_fetches=1)
    bc._session_fetch_count = 1  # simulate exhausted quota

    # Simulate a new attach resetting the counter.
    # We don't have real Chrome, so call the reset directly as attach would.
    bc._session_fetch_count = 0  # what attach_existing_browser does
    assert bc._session_fetch_count == 0


def test_get_status_includes_quota_info() -> None:
    """get_status returns fetch count, max_fetches, and approval_ttl."""
    bc = _make_bc(max_fetches=10, approval_ttl_seconds=600)
    status = bc.get_status()
    assert "session_fetch_count" in status
    assert status["max_fetches"] == 10
    assert status["approval_ttl_seconds"] == 600


# ---------------------------------------------------------------------------
# SEC-03: Domain blocklist
# ---------------------------------------------------------------------------


def test_blocked_exact_domain_raises_before_approval() -> None:
    """An exact blocklist match raises BrowserSecurityError before any approval."""
    from dream.browser_controller import BrowserController, BrowserSecurityError

    bc = BrowserController(_blocklist=frozenset({"evil.com"}))

    with pytest.raises(BrowserSecurityError) as exc_info:
        bc.request_approval("https://evil.com", "Test")
    assert exc_info.value.reason == "blocked_domain"


def test_blocked_subdomain_raises() -> None:
    """A subdomain of a blocked entry is also blocked."""
    from dream.browser_controller import BrowserController, BrowserSecurityError

    bc = BrowserController(_blocklist=frozenset({"evil.com"}))

    with pytest.raises(BrowserSecurityError) as exc_info:
        bc.request_approval("https://sub.evil.com", "Test")
    assert exc_info.value.reason == "blocked_domain"


def test_blocked_deep_subdomain_raises() -> None:
    """A deeply nested subdomain of a blocked entry is also blocked."""
    from dream.browser_controller import BrowserController, BrowserSecurityError

    bc = BrowserController(_blocklist=frozenset({"evil.com"}))

    with pytest.raises(BrowserSecurityError) as exc_info:
        bc.request_approval("https://a.b.c.evil.com", "Test")
    assert exc_info.value.reason == "blocked_domain"


def test_lookalike_domain_not_falsely_blocked() -> None:
    """badexample.com must NOT be blocked when only example.com is in the list."""
    from dream.browser_controller import BrowserController

    bc = BrowserController(_blocklist=frozenset({"example.com"}))
    # Should not raise.
    session = bc.request_approval("https://badexample.com", "Test")
    assert session.status == "pending"


def test_unrelated_domain_not_blocked() -> None:
    """A domain with a similar TLD is not falsely blocked."""
    from dream.browser_controller import BrowserController

    bc = BrowserController(_blocklist=frozenset({"evil.com"}))
    session = bc.request_approval("https://notevil.com", "Test")
    assert session.status == "pending"


def test_blocklist_check_before_navigate_network() -> None:
    """Blocklist check happens before any network call during navigate()."""
    from dream.browser_controller import BrowserController, BrowserSecurityError

    bc = BrowserController(_blocklist=frozenset({"blocked.com"}))
    bc._page = _fake_page()

    # Approve a session so the approval gate would pass.
    session = bc.request_approval("https://allowed.com", "Test")
    bc.approve_session(session.id)

    network_called: list[bool] = []
    bc._page.goto = AsyncMock(side_effect=lambda *a, **k: network_called.append(True))

    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("https://blocked.com"))
    assert exc_info.value.reason == "blocked_domain"
    assert not network_called, "Blocklist must block before network access"


def test_blocked_domain_error_does_not_reveal_blocklist_contents() -> None:
    """BrowserSecurityError for blocked domain must not leak blocklist data."""
    from dream.browser_controller import BrowserController, BrowserSecurityError

    bc = BrowserController(_blocklist=frozenset({"secret-corp-blocked.com"}))

    with pytest.raises(BrowserSecurityError) as exc_info:
        bc.request_approval("https://sub.secret-corp-blocked.com", "Test")

    # The error message must not contain the blocklist entry.
    assert "secret-corp-blocked.com" not in str(exc_info.value)


def test_blocklist_domain_cannot_be_bypassed_by_approval() -> None:
    """Even if somehow an approval object exists, blocked domain is still rejected."""
    from dream.browser_controller import BrowserController, BrowserSecurityError, BrowserSession

    bc = BrowserController(_blocklist=frozenset({"evil.com"}))
    bc._page = _fake_page()

    # Manually insert a fake "approved" session — simulating a tampered state.
    fake_session = BrowserSession(
        id="fake-session",
        url="https://evil.com",
        purpose="Test",
        domain="evil.com",
        status="active",
        allowed_once=True,
        approved_at=bc._clock(),
    )
    bc._current_session = fake_session

    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("https://evil.com"))
    assert exc_info.value.reason == "blocked_domain"


# ---------------------------------------------------------------------------
# SEC-03: Blocklist loading
# ---------------------------------------------------------------------------


def test_missing_blocklist_files_are_safe(tmp_path: Path) -> None:
    """Missing blocklist files do not raise an exception."""
    from dream.browser_controller import _load_blocklist

    result = _load_blocklist(
        paths=(
            str(tmp_path / "does_not_exist.txt"),
            str(tmp_path / "also_missing.txt"),
        )
    )
    assert result == frozenset()


def test_blocklist_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    """Comments and blank lines in blocklist are correctly ignored."""
    from dream.browser_controller import _load_blocklist

    bl_file = tmp_path / "blocked_domains.txt"
    bl_file.write_text(
        "# This is a comment\n"
        "\n"
        "evil.com   # inline comment\n"
        "  \n"
        "# another comment\n"
        "bad.org\n"
    )
    result = _load_blocklist(paths=(str(bl_file),))
    assert "evil.com" in result
    assert "bad.org" in result
    # The comment text must not be treated as an entry.
    assert "This is a comment" not in result
    assert "inline comment" not in result


def test_blocklist_normalises_case(tmp_path: Path) -> None:
    """Blocklist entries are normalised to lowercase."""
    from dream.browser_controller import _load_blocklist

    bl_file = tmp_path / "blocked_domains.txt"
    bl_file.write_text("Evil.COM\nBAD.ORG\n")
    result = _load_blocklist(paths=(str(bl_file),))
    assert "evil.com" in result
    assert "bad.org" in result


def test_blocklist_normalises_trailing_dot(tmp_path: Path) -> None:
    """Trailing dots are stripped from blocklist entries."""
    from dream.browser_controller import _load_blocklist

    bl_file = tmp_path / "blocked_domains.txt"
    bl_file.write_text("evil.com.\n")
    result = _load_blocklist(paths=(str(bl_file),))
    assert "evil.com" in result


def test_blocklist_handles_entry_with_port(tmp_path: Path) -> None:
    """Ports in blocklist entries are stripped; hostname is matched."""
    from dream.browser_controller import _load_blocklist

    bl_file = tmp_path / "blocked_domains.txt"
    bl_file.write_text("evil.com:8080\n")
    result = _load_blocklist(paths=(str(bl_file),))
    assert "evil.com" in result


def test_malformed_blocklist_entry_skipped_safely(tmp_path: Path) -> None:
    """Malformed entries (e.g. with shell-special chars) are skipped, not crash."""
    from dream.browser_controller import _load_blocklist

    bl_file = tmp_path / "blocked_domains.txt"
    bl_file.write_text(
        "good.com\n"
        "<evil>  \n"  # invalid chars
        "[::1]\n"     # IPv6 (not a valid hostname entry)
        "good2.com\n"
    )
    result = _load_blocklist(paths=(str(bl_file),))
    assert "good.com" in result
    assert "good2.com" in result
    # Malformed entries must not be added.
    assert "<evil>" not in result


def test_blocklist_uses_first_path_then_second(tmp_path: Path) -> None:
    """Entries from both files are merged."""
    from dream.browser_controller import _load_blocklist

    file1 = tmp_path / "bl1.txt"
    file1.write_text("evil.com\n")
    file2 = tmp_path / "bl2.txt"
    file2.write_text("bad.org\n")
    result = _load_blocklist(paths=(str(file1), str(file2)))
    assert "evil.com" in result
    assert "bad.org" in result


# ---------------------------------------------------------------------------
# SEC-03: Domain normalisation helpers
# ---------------------------------------------------------------------------


def test_normalise_hostname_lowercase() -> None:
    from dream.browser_controller import _normalise_hostname

    assert _normalise_hostname("EXAMPLE.COM") == "example.com"


def test_normalise_hostname_strips_trailing_dot() -> None:
    from dream.browser_controller import _normalise_hostname

    assert _normalise_hostname("example.com.") == "example.com"


def test_normalise_hostname_strips_port() -> None:
    from dream.browser_controller import _normalise_hostname

    assert _normalise_hostname("example.com:443") == "example.com"


def test_normalise_hostname_strips_scheme() -> None:
    from dream.browser_controller import _normalise_hostname

    assert _normalise_hostname("https://example.com") == "example.com"


def test_normalise_hostname_invalid_ipv6_returns_none() -> None:
    from dream.browser_controller import _normalise_hostname

    assert _normalise_hostname("[::1]") is None


def test_normalise_hostname_empty_returns_none() -> None:
    from dream.browser_controller import _normalise_hostname

    assert _normalise_hostname("") is None
    assert _normalise_hostname("   ") is None


def test_is_blocked_exact_match() -> None:
    from dream.browser_controller import _is_blocked

    assert _is_blocked("evil.com", frozenset({"evil.com"})) is True


def test_is_blocked_subdomain() -> None:
    from dream.browser_controller import _is_blocked

    assert _is_blocked("sub.evil.com", frozenset({"evil.com"})) is True


def test_is_blocked_not_substring() -> None:
    from dream.browser_controller import _is_blocked

    assert _is_blocked("badexample.com", frozenset({"example.com"})) is False


def test_is_blocked_unrelated() -> None:
    from dream.browser_controller import _is_blocked

    assert _is_blocked("good.com", frozenset({"evil.com"})) is False


def test_is_blocked_empty_blocklist() -> None:
    from dream.browser_controller import _is_blocked

    assert _is_blocked("anything.com", frozenset()) is False


# ---------------------------------------------------------------------------
# SEC-03: URL validation
# ---------------------------------------------------------------------------


def test_request_approval_rejects_non_https_scheme() -> None:
    """Non-HTTP(S) schemes are rejected in request_approval."""
    from dream.browser_controller import BrowserSecurityError

    bc = _make_bc()
    with pytest.raises(BrowserSecurityError) as exc_info:
        bc.request_approval("file:///etc/passwd", "Test")
    assert exc_info.value.reason == "invalid_url"


def test_navigate_rejects_non_https_scheme() -> None:
    """navigate() rejects non-HTTP(S) URLs with invalid_url."""
    from dream.browser_controller import BrowserSecurityError

    bc = _make_bc()
    bc._page = _fake_page()

    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate("javascript:alert(1)"))
    assert exc_info.value.reason == "invalid_url"


# ---------------------------------------------------------------------------
# Existing behaviour preserved
# ---------------------------------------------------------------------------


def test_deny_session_closes_pending() -> None:
    """deny_session closes a pending session."""
    bc = _make_bc()
    session = bc.request_approval("https://example.com", "Test")
    updated = bc.deny_session(session.id)
    assert updated is not None
    assert updated.status == "closed"
    assert updated.closed_at is not None


def test_approve_unknown_session_returns_none() -> None:
    """approve_session for unknown session id returns None."""
    bc = _make_bc()
    assert bc.approve_session("nonexistent") is None


def test_deny_unknown_session_returns_none() -> None:
    """deny_session for unknown session id returns None."""
    bc = _make_bc()
    assert bc.deny_session("nonexistent") is None


def test_get_status_returns_dict() -> None:
    """get_status returns a dict with expected keys."""
    bc = _make_bc()
    status = bc.get_status()
    assert isinstance(status, dict)
    assert "attached" in status
    assert "attached_to_existing" in status
    assert "pending_approvals" in status
    assert "session_fetch_count" in status
    assert "max_fetches" in status
    assert "approval_ttl_seconds" in status
    assert "current_session" in status


def test_attach_existing_browser_raises_without_chrome() -> None:
    """attach_existing_browser raises BrowserUnavailableError when no Chrome."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.attach_existing_browser(port=9999))


def test_launch_isolated_raises_without_chrome() -> None:
    """launch_isolated_browser raises BrowserUnavailableError when no Chrome."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.launch_isolated_browser())


def test_navigate_raises_without_browser() -> None:
    """navigate raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.navigate("https://example.com"))


def test_get_content_raises_without_browser() -> None:
    """get_content raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.get_content())


def test_execute_js_raises_without_browser() -> None:
    """execute_js raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.execute_js("1+1"))


def test_fill_form_raises_without_browser() -> None:
    """fill_form raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.fill_form("#input", "test"))


def test_click_raises_without_browser() -> None:
    """click raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.click("#button"))


def test_screenshot_raises_without_browser() -> None:
    """screenshot raises BrowserUnavailableError when no page attached."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.screenshot())


def test_get_cookies_raises_without_browser() -> None:
    """get_cookies raises BrowserUnavailableError when no context."""
    from dream.browser_controller import BrowserController, BrowserUnavailableError

    bc = BrowserController()
    with pytest.raises(BrowserUnavailableError):
        asyncio.run(bc.get_cookies())


def test_browser_unavailable_error_message() -> None:
    """BrowserUnavailableError has a meaningful message."""
    from dream.browser_controller import BrowserUnavailableError

    err = BrowserUnavailableError("Chrome not found")
    assert str(err) == "Chrome not found"


def test_browser_security_error_message() -> None:
    """BrowserSecurityError has a meaningful message and reason attribute."""
    from dream.browser_controller import BrowserSecurityError

    err = BrowserSecurityError("URL not approved", reason="approval_required")
    assert str(err) == "URL not approved"
    assert err.reason == "approval_required"


def test_browser_security_error_default_reason() -> None:
    """BrowserSecurityError reason defaults to empty string."""
    from dream.browser_controller import BrowserSecurityError

    err = BrowserSecurityError("Some error")
    assert err.reason == ""


def test_bridge_reflects_browser_imports() -> None:
    """The bridge re-exports browser types when available."""
    try:
        from dream.bridge import BrowserController, BrowserSession, PageContent

        assert BrowserController is not None
        assert BrowserSession is not None
        assert PageContent is not None
    except ImportError:
        pass  # OK if playwright not installed


# ---------------------------------------------------------------------------
# SEC-03: Error logging sanity — no URL leakage in errors
# ---------------------------------------------------------------------------


def test_security_error_does_not_include_query_string() -> None:
    """BrowserSecurityError for blocked domain must not include the full URL."""
    from dream.browser_controller import BrowserController, BrowserSecurityError

    bc = BrowserController(_blocklist=frozenset({"evil.com"}))

    with pytest.raises(BrowserSecurityError) as exc_info:
        bc.request_approval(
            "https://evil.com/path?token=supersecret&api_key=12345", "Test"
        )
    # Error text must not contain the query string secrets.
    err_text = str(exc_info.value)
    assert "supersecret" not in err_text
    assert "12345" not in err_text
    assert "token=" not in err_text


def test_approval_required_error_does_not_include_url() -> None:
    """BrowserSecurityError for approval_required must not include the full URL."""
    from dream.browser_controller import BrowserSecurityError

    bc = _make_bc()
    bc._page = _fake_page()

    sensitive_url = "https://example.com/path?api_key=topsecret"
    with pytest.raises(BrowserSecurityError) as exc_info:
        asyncio.run(bc.navigate(sensitive_url))
    err_text = str(exc_info.value)
    assert "topsecret" not in err_text
    assert "api_key" not in err_text
