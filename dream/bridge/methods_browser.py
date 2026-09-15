"""JSON-RPC bridge methods for Playwright / Deep Web Browser Automation subsystem."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from typing import Any
from urllib.parse import urlparse, urlsplit

from dream.bridge.errors import invalid_params
from dream.browser.engine import BrowserEngine
from dream.browser.types import BrowserBackendType

logger = logging.getLogger(__name__)

_GLOBAL_ENGINE: BrowserEngine | None = None

# SSRF and Domain Security Rules
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "::",
        "metadata.google.internal",
        "169.254.169.254",
        "metadata",
    }
)
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".corp")


def _get_engine() -> BrowserEngine:
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None or not _GLOBAL_ENGINE.is_active:
        _GLOBAL_ENGINE = BrowserEngine(backend_type=BrowserBackendType.MOCK, headless=True)
    return _GLOBAL_ENGINE


def _validate_safe_url(url: str) -> str:
    """Ensure target URL is valid, public http(s), and not an SSRF/loopback target."""
    raw = (url or "").strip()
    if not raw:
        raise invalid_params("url must be a non-empty string")
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise invalid_params(f"Only HTTP/HTTPS URLs are allowed, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise invalid_params("Invalid URL: missing hostname")

    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS or any(host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        raise invalid_params(f"Access to local/internal host {host!r} is refused (SSRF protection)")

    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise invalid_params(
                f"Access to private/loopback IP {host!r} is refused (SSRF protection)"
            )
    except ValueError:
        pass  # Named hostname, not IP literal

    return raw


async def browser_get_status(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return status of active browser session."""
    del params
    engine = _get_engine()
    status = engine.get_status()
    return {
        "status": "healthy" if status.is_active else "inactive",
        "session": status.to_dict(),
        "blocklist_count": len(engine.blocklist),
    }


async def browser_launch(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Initialize / launch a browser session."""
    global _GLOBAL_ENGINE
    params = params or {}
    backend_str = str(params.get("backend", "mock")).lower()
    headless = bool(params.get("headless", True))

    backend = BrowserBackendType.MOCK
    if backend_str == "playwright":
        backend = BrowserBackendType.PLAYWRIGHT
    elif backend_str == "cdp":
        backend = BrowserBackendType.CDP
    elif backend_str == "stealth":
        backend = BrowserBackendType.STEALTH

    _GLOBAL_ENGINE = BrowserEngine(backend_type=backend, headless=headless)
    status = _GLOBAL_ENGINE.get_status()
    return {
        "status": "launched",
        "session": status.to_dict(),
    }


async def browser_navigate(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Navigate to target URL with SSRF protection and DOM parsing."""
    params = params or {}
    url_input = params.get("url")
    if not isinstance(url_input, str) or not url_input.strip():
        raise invalid_params("url must be a non-empty string")

    safe_url = _validate_safe_url(url_input)
    engine = _get_engine()

    snapshot = await asyncio.to_thread(engine.navigate, safe_url)
    return {
        "status": "navigated",
        "snapshot": snapshot.to_dict(),
    }


async def browser_click(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Click an element by CSS selector."""
    params = params or {}
    selector = params.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        raise invalid_params("selector must be a non-empty string")

    engine = _get_engine()
    res = await asyncio.to_thread(engine.click, selector.strip())
    return {
        "status": "clicked",
        "result": res,
    }


async def browser_type_text(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Type text into an element matching selector."""
    params = params or {}
    selector = params.get("selector")
    text = params.get("text")
    if not isinstance(selector, str) or not selector.strip():
        raise invalid_params("selector must be a non-empty string")
    if not isinstance(text, str):
        raise invalid_params("text must be a string")

    engine = _get_engine()
    res = await asyncio.to_thread(engine.type_text, selector.strip(), text)
    return {
        "status": "typed",
        "result": res,
    }


async def browser_screenshot(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Capture page screenshot and return local path."""
    params = params or {}
    path = params.get("path")
    if path is not None and not isinstance(path, str):
        raise invalid_params("path must be a string")

    engine = _get_engine()
    shot_path = await asyncio.to_thread(engine.take_screenshot, path)
    return {
        "status": "captured",
        "screenshot_path": shot_path,
        "timestamp": time.time(),
    }


async def browser_extract_content(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract semantic Markdown, links, and interactive elements from current page."""
    del params
    engine = _get_engine()
    snapshot = await asyncio.to_thread(engine.extract_content)
    return {
        "status": "extracted",
        "snapshot": snapshot.to_dict(),
    }


async def browser_deep_crawl(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Autonomous goal-directed deep crawling of URL domain."""
    params = params or {}
    url_input = params.get("url")
    if not isinstance(url_input, str) or not url_input.strip():
        raise invalid_params("url must be a non-empty string")

    safe_url = _validate_safe_url(url_input)
    goal = str(params.get("goal") or "Extract general knowledge and API documentation").strip()
    max_depth = min(3, max(1, int(params.get("max_depth", 2))))
    max_pages = min(10, max(1, int(params.get("max_pages", 5))))

    engine = _get_engine()
    parsed_root = urlparse(safe_url)
    root_domain = parsed_root.hostname or "domain"

    visited: set[str] = set()
    crawl_queue: list[tuple[str, int]] = [(safe_url, 1)]
    pages_extracted: list[dict[str, Any]] = []
    link_graph: list[dict[str, str]] = []

    while crawl_queue and len(pages_extracted) < max_pages:
        current_url, depth = crawl_queue.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            snapshot = await asyncio.to_thread(engine.navigate, current_url)
            page_summary = {
                "url": current_url,
                "title": snapshot.title,
                "depth": depth,
                "status_code": snapshot.status_code,
                "elements_count": len(snapshot.elements),
                "content_preview": snapshot.content_markdown[:300],
                "markdown": snapshot.content_markdown,
            }
            pages_extracted.append(page_summary)

            # Discover links on page
            if depth < max_depth:
                for elem in snapshot.elements:
                    if elem.tag_name == "a" and "href" in elem.attributes:
                        href = elem.attributes["href"]
                        if href.startswith("/"):
                            href = f"{parsed_root.scheme}://{parsed_root.netloc}{href}"
                        if href.startswith("http") and root_domain in href and href not in visited:
                            link_graph.append(
                                {"source": current_url, "target": href, "text": elem.text}
                            )
                            crawl_queue.append((href, depth + 1))
        except Exception as exc:
            logger.warning("Deep crawl error at %s: %s", current_url, exc)

    synthesis_msg = (
        f"Crawled {len(pages_extracted)} pages under domain {root_domain}. "
        f"Discovered {len(link_graph)} internal link relations for goal: '{goal}'."
    )
    return {
        "status": "crawled",
        "root_url": safe_url,
        "goal": goal,
        "total_pages": len(pages_extracted),
        "pages": pages_extracted,
        "link_graph": link_graph[:30],
        "synthesis": synthesis_msg,
    }


async def browser_close(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Close active browser session."""
    del params
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE:
        _GLOBAL_ENGINE.close()
        _GLOBAL_ENGINE = None
    return {"status": "closed"}


async def browser_reset(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reset browser engine state for clean test isolation."""
    del params
    global _GLOBAL_ENGINE
    _GLOBAL_ENGINE = BrowserEngine(backend_type=BrowserBackendType.MOCK, headless=True)
    return {"status": "reset"}


HANDLERS = {
    "browser.get_status": browser_get_status,
    "browser.launch": browser_launch,
    "browser.navigate": browser_navigate,
    "browser.click": browser_click,
    "browser.type_text": browser_type_text,
    "browser.screenshot": browser_screenshot,
    "browser.extract_content": browser_extract_content,
    "browser.deep_crawl": browser_deep_crawl,
    "browser.close": browser_close,
    "browser.reset": browser_reset,
}
