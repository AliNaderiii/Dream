"""Agent tool definitions for Web Search and Content Extraction."""

from __future__ import annotations

import json

from dream.web.manager import WebManager
from dream.web.types import SearchBackendType

_GLOBAL_WEB_MANAGER: WebManager | None = None


def get_web_manager() -> WebManager:
    """Retrieve or initialize singleton WebManager."""
    global _GLOBAL_WEB_MANAGER
    if _GLOBAL_WEB_MANAGER is None:
        _GLOBAL_WEB_MANAGER = WebManager()
    return _GLOBAL_WEB_MANAGER


def reset_web_manager() -> None:
    """Reset global WebManager instance for isolated testing."""
    global _GLOBAL_WEB_MANAGER
    _GLOBAL_WEB_MANAGER = None


def web_search(
    query: str,
    backend: str | None = None,
    max_results: int = 5,
) -> str:
    """Search the live web across DuckDuckGo, Tavily, Brave, or Firecrawl.

    Args:
        query: Search query string.
        backend: Optional search provider ('duckduckgo', 'tavily', 'brave', 'firecrawl').
        max_results: Maximum number of search results to return (default: 5).
    """
    mgr = get_web_manager()
    b_type = SearchBackendType(backend.lower()) if backend else None
    response = mgr.search(query, backend_type=b_type, max_results=max_results)
    return json.dumps(response.to_dict(), ensure_ascii=False, indent=2)


def web_extract(
    url: str,
    max_chars: int = 8000,
) -> str:
    """Extract, clean, and convert web page content to Markdown with security guards.

    Args:
        url: Public web page URL (http/https).
        max_chars: Character budget for the extracted Markdown (default: 8000).
    """
    mgr = get_web_manager()
    content = mgr.extract_url(url, max_chars=max_chars)
    return json.dumps(content.to_dict(), ensure_ascii=False, indent=2)


def web_list_search_backends() -> str:
    """List all registered search backends and their availability."""
    mgr = get_web_manager()
    backends = mgr.list_backends()
    return json.dumps({"search_backends": backends}, ensure_ascii=False, indent=2)


def web_switch_search_backend(backend: str) -> str:
    """Switch active default web search backend."""
    mgr = get_web_manager()
    ok = mgr.set_active_backend(backend)
    if ok:
        return f"Active search backend switched to: {backend}"
    return f"Failed to switch to search backend: {backend}."
