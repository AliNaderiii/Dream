"""``webbrowser.*`` JSON-RPC bridge methods — the REAL browser controller.

Discovered automatically by :mod:`dream.bridge.extensions`.

=================================  ==================================================
``webbrowser.status``             Honest controller status + playwright availability
``webbrowser.attach``             Attach to the user's Chrome (CDP, port 9222)
``webbrowser.launch``             Launch a fresh isolated Chrome (visible)
``webbrowser.request``            Create a navigation approval request (pending)
``webbrowser.approve``            Approve a pending navigation (single-use, TTL)
``webbrowser.deny``              Deny a pending navigation
``webbrowser.navigate``           Real navigation → page content (approval-gated)
``webbrowser.content``            Re-extract the current page content
``webbrowser.click``              Click an element by CSS selector
``webbrowser.fill``               Type text into an element
``webbrowser.screenshot``         Full-page screenshot (local file)
``webbrowser.close``              Close the browser session
=================================  ==================================================

This wraps :class:`dream.browser_controller.BrowserController` — the real
Playwright/CDP engine with the SEC-03 security model (every navigation needs
an explicit, single-use, expiring user approval; per-session quota; fail-closed
domain blocklist). The legacy ``browser.*`` extension methods drive a mock
engine and stay unwired by design; everything here is real or says so.

Playwright is an optional extra (``pip install ".[browser]"``). When it is
absent the methods answer honestly with ``available: false`` and an install
hint — never a fake page.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any

from dream.bridge.errors import invalid_params

logger = logging.getLogger(__name__)

__all__ = ["HANDLERS"]

try:  # optional heavy import, guarded for honest availability reporting
    from dream.browser_controller import (  # noqa: F401
        BrowserController,
        BrowserSecurityError,
        BrowserTimeoutError,
        BrowserUnavailableError,
    )
    _CORE_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on the environment
    BrowserController = None  # type: ignore[assignment,misc]
    BrowserSecurityError = RuntimeError  # type: ignore[assignment,misc]
    BrowserTimeoutError = RuntimeError  # type: ignore[assignment,misc]
    BrowserUnavailableError = RuntimeError  # type: ignore[assignment,misc]
    _CORE_IMPORT_ERROR = str(exc)

INSTALL_HINT = 'playwright is not installed — install with: pip install ".[browser]"'

_GLOBAL_CONTROLLER: Any = None
_CONTROLLER_LOCK = asyncio.Lock()


def _playwright_available() -> bool:
    if _CORE_IMPORT_ERROR:
        return False
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    return True


def _controller() -> Any:
    global _GLOBAL_CONTROLLER
    if _GLOBAL_CONTROLLER is None:
        _GLOBAL_CONTROLLER = BrowserController()
    return _GLOBAL_CONTROLLER


def _reset_controller() -> None:
    """Test isolation seam."""
    global _GLOBAL_CONTROLLER
    _GLOBAL_CONTROLLER = None


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _string(data: dict[str, Any], key: str, *, required: bool = True, limit: int = 4_096) -> str:
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise invalid_params(f"{key} must be a non-empty string of at most {limit} characters")
    return value.strip()


def _content_dict(content: Any) -> dict[str, Any]:
    return dataclasses.asdict(content)


def _fail(exc: Exception) -> dict[str, Any]:
    reason = getattr(exc, "reason", "")
    return {"success": False, "error": str(exc), "reason": reason or None}


async def webbrowser_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Honest status: playwright availability + the real controller state."""
    del params, kwargs
    available = _playwright_available()
    payload: dict[str, Any] = {"success": True, "available": available}
    if not available:
        payload["error"] = INSTALL_HINT
        payload["controller"] = None
        return payload
    status = await asyncio.to_thread(_controller().get_status)
    payload["controller"] = status
    return payload


async def webbrowser_attach(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Attach to the user's running Chrome. Params: ``port`` (default 9222)."""
    data = _params(params, kwargs)
    port = data.get("port", 9222)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise invalid_params("port must be an integer between 1 and 65535")
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        info = await _controller().attach_existing_browser(port=port)
    except BrowserUnavailableError as exc:
        return _fail(exc)
    logger.info("webbrowser.attach ok (port %d)", port)
    return {"success": True, "available": True, **info}


async def webbrowser_launch(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Launch a fresh isolated Chrome (visible, no user profile)."""
    del params, kwargs
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        info = await _controller().launch_isolated_browser()
    except BrowserUnavailableError as exc:
        return _fail(exc)
    logger.info("webbrowser.launch ok (isolated)")
    return {"success": True, "available": True, **info}


async def webbrowser_request(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Create a pending navigation approval. Params: ``url``, ``purpose``."""
    data = _params(params, kwargs)
    url = _string(data, "url", limit=2_048)
    purpose = _string(data, "purpose", required=False, limit=500) or "مرور وب"
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        session = await asyncio.to_thread(_controller().request_approval, url, purpose)
    except BrowserSecurityError as exc:
        return _fail(exc)
    return {"success": True, "session": dataclasses.asdict(session)}


async def webbrowser_approve(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Approve a pending navigation (single-use, expires per TTL)."""
    data = _params(params, kwargs)
    session_id = _string(data, "session_id", limit=80)
    session = await asyncio.to_thread(_controller().approve_session, session_id)
    if session is None:
        return {"success": False, "error": f"no pending session with id '{session_id}'"}
    return {"success": True, "session": dataclasses.asdict(session)}


async def webbrowser_deny(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Deny a pending navigation."""
    data = _params(params, kwargs)
    session_id = _string(data, "session_id", limit=80)
    session = await asyncio.to_thread(_controller().deny_session, session_id)
    if session is None:
        return {"success": False, "error": f"no pending session with id '{session_id}'"}
    return {"success": True, "session": dataclasses.asdict(session)}


async def webbrowser_navigate(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Navigate for real. Params: ``url``, ``purpose``, ``timeout`` (s).

    When the security model requires (or has expired) an approval, the result
    is ``status: "approval_required"`` with the pending session — the UI shows
    an approve/deny card and retries. No navigation happens without it.
    """
    data = _params(params, kwargs)
    url = _string(data, "url", limit=2_048)
    purpose = _string(data, "purpose", required=False, limit=500) or "مرور وب"
    timeout = data.get("timeout", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 120:
        raise invalid_params("timeout must be an integer between 5 and 120 seconds")
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        content = await _controller().navigate(url, purpose=purpose, timeout=timeout)
    except BrowserSecurityError as exc:
        reason = getattr(exc, "reason", "")
        if reason in ("approval_required", "approval_expired"):
            status = await asyncio.to_thread(_controller().get_status)
            return {
                "success": False,
                "status": reason,
                "session": status.get("current_session"),
                "error": str(exc),
            }
        return _fail(exc)
    except (BrowserUnavailableError, BrowserTimeoutError) as exc:
        return _fail(exc)
    logger.info("webbrowser.navigate ok (host logged by controller)")
    return {"success": True, "content": _content_dict(content)}


async def webbrowser_content(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Re-extract the current page content."""
    del params, kwargs
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        content = await _controller().get_content()
    except (BrowserUnavailableError, BrowserTimeoutError) as exc:
        return _fail(exc)
    return {"success": True, "content": _content_dict(content)}


async def webbrowser_click(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Click an element. Params: ``selector`` (CSS)."""
    data = _params(params, kwargs)
    selector = _string(data, "selector", limit=500)
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        await _controller().click(selector)
    except BrowserUnavailableError as exc:
        return _fail(exc)
    except Exception as exc:  # selector miss / playwright errors — safe to show
        return _fail(exc)
    return {"success": True, "clicked": selector}


async def webbrowser_fill(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Type text into an element. Params: ``selector``, ``value``."""
    data = _params(params, kwargs)
    selector = _string(data, "selector", limit=500)
    value = data.get("value")
    if not isinstance(value, str) or len(value) > 10_000:
        raise invalid_params("value must be a string of at most 10000 characters")
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        await _controller().fill_form(selector, value)
    except BrowserUnavailableError as exc:
        return _fail(exc)
    except Exception as exc:
        return _fail(exc)
    return {"success": True, "filled": selector}


async def webbrowser_screenshot(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Full-page screenshot into the local screenshots dir. Params: ``path``."""
    data = _params(params, kwargs)
    path = data.get("path", "")
    if path is None:
        path = ""
    if not isinstance(path, str) or len(path) > 4_096:
        raise invalid_params("path must be a string of at most 4096 characters")
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    try:
        shot = await _controller().screenshot(path or None)
    except BrowserUnavailableError as exc:
        return _fail(exc)
    except Exception as exc:
        return _fail(exc)
    return {"success": True, "screenshot_path": str(shot)}


async def webbrowser_close(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Close the browser session."""
    del params, kwargs
    if not _playwright_available():
        return {"success": False, "available": False, "error": INSTALL_HINT}
    await _controller().close()
    return {"success": True, "closed": True}


HANDLERS = {
    "webbrowser.status": webbrowser_status,
    "webbrowser.attach": webbrowser_attach,
    "webbrowser.launch": webbrowser_launch,
    "webbrowser.request": webbrowser_request,
    "webbrowser.approve": webbrowser_approve,
    "webbrowser.deny": webbrowser_deny,
    "webbrowser.navigate": webbrowser_navigate,
    "webbrowser.content": webbrowser_content,
    "webbrowser.click": webbrowser_click,
    "webbrowser.fill": webbrowser_fill,
    "webbrowser.screenshot": webbrowser_screenshot,
    "webbrowser.close": webbrowser_close,
}
