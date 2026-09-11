"""Multi-Provider Browser Automation, DOM Parsing & Vision subsystem for Dream Agent."""

from __future__ import annotations

from dream.browser.dom import DOMParser
from dream.browser.engine import BrowserEngine
from dream.browser.slash import handle_browser_command
from dream.browser.tools import (
    browser_click,
    browser_close,
    browser_extract_content,
    browser_get_status,
    browser_navigate,
    browser_screenshot,
    browser_type,
    get_browser_tools,
    get_global_browser_engine,
    reset_global_browser_engine,
)
from dream.browser.types import (
    BrowserActionType,
    BrowserBackendType,
    BrowserSessionStatus,
    PageElement,
    PageSnapshot,
)

__all__ = [
    "BrowserActionType",
    "BrowserBackendType",
    "BrowserEngine",
    "BrowserSessionStatus",
    "DOMParser",
    "PageElement",
    "PageSnapshot",
    "browser_click",
    "browser_close",
    "browser_extract_content",
    "browser_get_status",
    "browser_navigate",
    "browser_screenshot",
    "browser_type",
    "get_browser_tools",
    "get_global_browser_engine",
    "handle_browser_command",
    "reset_global_browser_engine",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "browser" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "browser",
            [
                "browser_navigate",
                "browser_click",
                "browser_type",
                "browser_screenshot",
                "browser_extract_content",
                "browser_close",
                "browser_get_status",
            ],
            description="Multi-driver browser control, DOM extraction, and visual interaction",
        )
except Exception:
    pass
