"""LLM Tool bindings for Browser Automation and Vision interaction."""

from __future__ import annotations

from typing import Any

from dream.browser.engine import BrowserEngine

_GLOBAL_BROWSER_ENGINE: BrowserEngine | None = None


def get_global_browser_engine() -> BrowserEngine:
    """Get or create singleton BrowserEngine."""
    global _GLOBAL_BROWSER_ENGINE
    if _GLOBAL_BROWSER_ENGINE is None:
        _GLOBAL_BROWSER_ENGINE = BrowserEngine()
    return _GLOBAL_BROWSER_ENGINE


def reset_global_browser_engine() -> None:
    """Reset singleton instance for testing."""
    global _GLOBAL_BROWSER_ENGINE
    _GLOBAL_BROWSER_ENGINE = None


def browser_navigate(url: str) -> dict[str, Any]:
    """Navigate browser to a URL, returning page title, content, and interactive elements."""
    engine = get_global_browser_engine()
    snapshot = engine.navigate(url)
    return snapshot.to_dict()


def browser_click(selector: str) -> dict[str, Any]:
    """Click on a specific button, link, or input element by CSS selector or text label."""
    engine = get_global_browser_engine()
    return engine.click(selector)


def browser_type(selector: str, text: str) -> dict[str, Any]:
    """Type text into a designated input field or textarea."""
    engine = get_global_browser_engine()
    return engine.type_text(selector, text)


def browser_screenshot(file_path: str = "") -> dict[str, Any]:
    """Capture a screenshot of the currently visible web page and save to disk."""
    engine = get_global_browser_engine()
    path = engine.take_screenshot(file_path if file_path else None)
    return {"success": True, "screenshot_path": path, "url": engine.current_url}


def browser_extract_content() -> dict[str, Any]:
    """Extract full simplified Markdown text and interactable element tree from current page."""
    engine = get_global_browser_engine()
    snapshot = engine.extract_content()
    return snapshot.to_dict()


def browser_close() -> dict[str, Any]:
    """Close active browser session and release memory."""
    engine = get_global_browser_engine()
    success = engine.close()
    return {"success": success, "message": "Browser session closed."}


def browser_get_status() -> dict[str, Any]:
    """Retrieve runtime diagnostics and URL status for active browser session."""
    engine = get_global_browser_engine()
    status = engine.get_status()
    return status.to_dict()


def get_browser_tools() -> list[Any]:
    """Return list of browser automation tool functions for agent binding."""
    return [
        browser_navigate,
        browser_click,
        browser_type,
        browser_screenshot,
        browser_extract_content,
        browser_close,
        browser_get_status,
    ]
