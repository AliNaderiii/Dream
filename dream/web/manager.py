"""Central Web Search and Content Extraction Manager with fallback cascade."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from dream.web.extractor import WebContentExtractor
from dream.web.search import (
    BaseSearchBackend,
    BraveSearchBackend,
    DuckDuckGoSearchBackend,
    FirecrawlSearchBackend,
    MockSearchBackend,
    TavilySearchBackend,
)
from dream.web.types import (
    ExtractedWebContent,
    SearchBackendType,
    SearchResponse,
)

logger = logging.getLogger(__name__)


class WebManager:
    """Orchestrates search provider registry, fallback routing, and web extraction."""

    def __init__(
        self,
        default_backend: SearchBackendType = SearchBackendType.DUCKDUCKGO,
        cache_ttl_seconds: int = 900,
    ) -> None:
        self.active_backend_type = default_backend
        self.cache_ttl_seconds = cache_ttl_seconds
        self.extractor = WebContentExtractor()
        self._lock = threading.RLock()
        self._backends: dict[SearchBackendType, BaseSearchBackend] = {}
        self._cache: dict[str, tuple[float, SearchResponse]] = {}

        # Register standard built-in backends
        self.register_backend(DuckDuckGoSearchBackend())
        self.register_backend(TavilySearchBackend())
        self.register_backend(BraveSearchBackend())
        self.register_backend(FirecrawlSearchBackend())
        self.register_backend(MockSearchBackend())

    def register_backend(self, backend: BaseSearchBackend) -> None:
        """Register a search provider."""
        with self._lock:
            self._backends[backend.backend_type] = backend

    def get_backend(
        self,
        backend_type: SearchBackendType | None = None,
    ) -> BaseSearchBackend | None:
        """Retrieve backend by type or active default."""
        with self._lock:
            target = backend_type or self.active_backend_type
            return self._backends.get(target)

    def set_active_backend(self, backend: SearchBackendType | str) -> bool:
        """Switch active search provider."""
        with self._lock:
            if isinstance(backend, str):
                try:
                    backend = SearchBackendType(backend.lower())
                except ValueError:
                    logger.error(f"Unknown search backend: {backend}")
                    return False

            if backend not in self._backends:
                return False

            self.active_backend_type = backend
            logger.info(f"Active search backend set to: {backend.value}")
            return True

    def search(
        self,
        query: str,
        backend_type: SearchBackendType | None = None,
        max_results: int = 5,
        use_cache: bool = True,
    ) -> SearchResponse:
        """Execute search with caching and fallback cascade."""
        clean_query = query.strip()
        cache_key = f"{backend_type or self.active_backend_type}:{clean_query}:{max_results}"

        with self._lock:
            if use_cache and cache_key in self._cache:
                timestamp, cached_res = self._cache[cache_key]
                if time.time() - timestamp < self.cache_ttl_seconds:
                    return cached_res

        # 1. Primary backend search
        primary = self.get_backend(backend_type)
        if primary and primary.is_available():
            res = primary.search(clean_query, max_results=max_results)
            if res.is_success and res.results:
                self._store_cache(cache_key, res)
                return res
            logger.warning(
                f"Primary search backend '{primary.backend_type.value}' failed. "
                "Triggering fallback..."
            )

        # 2. Fallback cascade across other available backends
        with self._lock:
            available_fallbacks = [
                b for b in self._backends.values()
                if b.backend_type != (backend_type or self.active_backend_type) and b.is_available()
            ]

        for fb in available_fallbacks:
            logger.info(f"Cascading search to fallback backend: {fb.backend_type.value}")
            res = fb.search(clean_query, max_results=max_results)
            if res.is_success and res.results:
                self._store_cache(cache_key, res)
                return res

        # If all backends fail, return empty response
        return SearchResponse(
            query=clean_query,
            backend=backend_type or self.active_backend_type,
            error_message="All search backends failed to retrieve results.",
        )

    def extract_url(self, url: str, max_chars: int = 8000) -> ExtractedWebContent:
        """Extract Markdown content from web URL."""
        return self.extractor.extract_from_url(url, max_chars=max_chars)

    def list_backends(self) -> list[dict[str, Any]]:
        """Return diagnostic metrics of all search backends."""
        with self._lock:
            items = []
            for b_type, b in self._backends.items():
                items.append({
                    "type": b_type.value,
                    "is_active": b_type == self.active_backend_type,
                    "available": b.is_available(),
                })
            return items

    def _store_cache(self, key: str, res: SearchResponse) -> None:
        """Write item to search cache."""
        with self._lock:
            self._cache[key] = (time.time(), res)
