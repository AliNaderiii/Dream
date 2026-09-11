"""Dream Multi-Provider Web Search, Extraction, and Security Engine."""

from dream.web.extractor import WebContentExtractor
from dream.web.manager import WebManager
from dream.web.search import (
    BaseSearchBackend,
    BraveSearchBackend,
    DuckDuckGoSearchBackend,
    FirecrawlSearchBackend,
    MockSearchBackend,
    TavilySearchBackend,
)
from dream.web.security import SSRFSecurityViolation, sanitize_extracted_web_text, validate_web_url
from dream.web.slash import handle_browse_command, handle_search_command
from dream.web.tools import (
    get_web_manager,
    reset_web_manager,
    web_extract,
    web_list_search_backends,
    web_search,
    web_switch_search_backend,
)
from dream.web.types import (
    ExtractedWebContent,
    SearchBackendType,
    SearchResponse,
    SearchResultItem,
)

__all__ = [
    "WebContentExtractor",
    "WebManager",
    "BaseSearchBackend",
    "DuckDuckGoSearchBackend",
    "TavilySearchBackend",
    "BraveSearchBackend",
    "FirecrawlSearchBackend",
    "MockSearchBackend",
    "SearchBackendType",
    "SearchResponse",
    "SearchResultItem",
    "ExtractedWebContent",
    "SSRFSecurityViolation",
    "validate_web_url",
    "sanitize_extracted_web_text",
    "get_web_manager",
    "reset_web_manager",
    "web_search",
    "web_extract",
    "web_list_search_backends",
    "web_switch_search_backend",
    "handle_search_command",
    "handle_browse_command",
]
