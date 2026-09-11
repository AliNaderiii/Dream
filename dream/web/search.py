"""Multi-provider Web Search backends (DuckDuckGo, Tavily, Brave, Firecrawl, Mock)."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from dream.web.types import (
    SearchBackendType,
    SearchResponse,
    SearchResultItem,
)

logger = logging.getLogger(__name__)

USER_AGENT = "DreamAssistant/2.0 (Search Engine; +https://github.com/AliNaderiii/Dream)"


class BaseSearchBackend(ABC):
    """Abstract base class for all Web Search providers."""

    def __init__(self, backend_type: SearchBackendType) -> None:
        self.backend_type = backend_type

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        """Perform search query and return normalized results."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend credentials or endpoints are available."""
        raise NotImplementedError


class MockSearchBackend(BaseSearchBackend):
    """Deterministic offline search backend for testing and CI."""

    def __init__(self, predefined_results: list[SearchResultItem] | None = None) -> None:
        super().__init__(SearchBackendType.MOCK)
        self.predefined_results = predefined_results or [
            SearchResultItem(
                title="Dream Assistant Official",
                url="https://github.com/AliNaderiii/Dream",
                snippet="An advanced, Persian-first agentic AI assistant.",
                score=0.99,
            ),
            SearchResultItem(
                title="Hermes Agent Framework",
                url="https://hermes-agent.nousresearch.com",
                snippet="Open-source agentic framework by Nous Research.",
                score=0.95,
            ),
        ]

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        results = [
            r for r in self.predefined_results
            if query.lower() in r.title.lower() or query.lower() in r.snippet.lower()
        ]
        if not results:
            results = self.predefined_results[:max_results]
        return SearchResponse(
            query=query,
            backend=self.backend_type,
            results=results[:max_results],
            total_found=len(results),
            duration_ms=1.2,
        )


class DuckDuckGoSearchBackend(BaseSearchBackend):
    """Zero-configuration search backend using DuckDuckGo HTML / Lite endpoints."""

    def __init__(self) -> None:
        super().__init__(SearchBackendType.DUCKDUCKGO)

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        start = time.perf_counter()
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "fa,en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                html_body = resp.read().decode("utf-8", errors="replace")

            # Parse results from DuckDuckGo HTML
            results: list[SearchResultItem] = []
            import re
            s_pat = r'<a class="result__snippet[^>]*>(.*?)</a>'
            u_pat = r'<a class="result__url[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            snippets = re.findall(s_pat, html_body, re.DOTALL)
            titles = re.findall(u_pat, html_body, re.DOTALL)

            for i, (link, title) in enumerate(titles):
                if i >= max_results:
                    break
                snippet = snippets[i] if i < len(snippets) else ""
                clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                clean_title = re.sub(r"<[^>]+>", "", title).strip() or "Web Result"

                results.append(
                    SearchResultItem(
                        title=clean_title,
                        url=link.strip(),
                        snippet=clean_snippet,
                        score=round(1.0 - (i * 0.1), 2),
                    )
                )

            duration_ms = (time.perf_counter() - start) * 1000
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                results=results,
                total_found=len(results),
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"DuckDuckGo search error: {exc}")
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                results=[],
                total_found=0,
                duration_ms=duration_ms,
                error_message=str(exc),
            )


class TavilySearchBackend(BaseSearchBackend):
    """Deep research and LLM-optimized search backend using Tavily API."""

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(SearchBackendType.TAVILY)
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        start = time.perf_counter()
        if not self.is_available():
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                error_message="TAVILY_API_KEY is not configured in environment.",
            )

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": True,
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items: list[SearchResultItem] = []
            for item in data.get("results", []):
                items.append(
                    SearchResultItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        score=item.get("score", 0.0),
                        published_date=item.get("published_date"),
                    )
                )

            duration_ms = (time.perf_counter() - start) * 1000
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                results=items,
                total_found=len(items),
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                error_message=f"Tavily search failed: {exc}",
                duration_ms=duration_ms,
            )


class BraveSearchBackend(BaseSearchBackend):
    """Independent web search index using Brave Search API."""

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(SearchBackendType.BRAVE)
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        start = time.perf_counter()
        if not self.is_available():
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                error_message="BRAVE_API_KEY is not configured.",
            )

        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://api.search.brave.com/res/v1/web/search?q={encoded_query}&count={max_results}"

        try:
            req = urllib.request.Request(
                url,
                headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items: list[SearchResultItem] = []
            for item in data.get("web", {}).get("results", []):
                items.append(
                    SearchResultItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("description", ""),
                    )
                )

            duration_ms = (time.perf_counter() - start) * 1000
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                results=items,
                total_found=len(items),
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                error_message=f"Brave search failed: {exc}",
                duration_ms=duration_ms,
            )


class FirecrawlSearchBackend(BaseSearchBackend):
    """Deep scraping and dynamic web crawling search using Firecrawl API."""

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(SearchBackendType.FIRECRAWL)
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        start = time.perf_counter()
        if not self.is_available():
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                error_message="FIRECRAWL_API_KEY is not configured.",
            )

        url = "https://api.firecrawl.dev/v1/search"
        payload = {"query": query, "limit": max_results}

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items: list[SearchResultItem] = []
            for item in data.get("data", []):
                items.append(
                    SearchResultItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("description", "") or item.get("markdown", "")[:300],
                    )
                )

            duration_ms = (time.perf_counter() - start) * 1000
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                results=items,
                total_found=len(items),
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return SearchResponse(
                query=query,
                backend=self.backend_type,
                error_message=f"Firecrawl search failed: {exc}",
                duration_ms=duration_ms,
            )
