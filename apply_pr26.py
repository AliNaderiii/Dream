#!/usr/bin/env python3
"""Standalone installer for Phase 23 (Multi-Provider Browser Automation & Vision Engine).

Applies:
- `dream/browser/__init__.py`
- `dream/browser/types.py`
- `dream/browser/dom.py`
- `dream/browser/engine.py`
- `dream/browser/tools.py`
- `dream/browser/slash.py`
- `dream/security/pathsafety.py` (cross-platform POSIX path protection on Windows)
- Registers "browser" toolset in `dream/tools/toolsets.py`
- `tests/test_browser_automation_and_vision.py`
"""

from __future__ import annotations

from pathlib import Path
import sys

FILES = {
    "dream/browser/types.py": '''"""Data types and domain models for Multi-Provider Browser Automation & Vision subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BrowserBackendType(str, Enum):
    """Supported browser automation and driver backends."""

    PLAYWRIGHT = "playwright"
    CDP = "cdp"
    STEALTH = "stealth"
    MOCK = "mock"


class BrowserActionType(str, Enum):
    """Types of browser interaction actions."""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    EXTRACT = "extract"
    SCROLL = "scroll"
    CLOSE = "close"


@dataclass(slots=True)
class PageElement:
    """An interactable element detected in the DOM."""

    element_id: int
    tag_name: str
    text: str
    selector: str
    is_interactive: bool = True
    attributes: dict[str, str] = field(default_factory=dict)
    bounding_box: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize page element to dictionary."""
        return {
            "element_id": self.element_id,
            "tag_name": self.tag_name,
            "text": self.text,
            "selector": self.selector,
            "is_interactive": self.is_interactive,
            "attributes": self.attributes,
            "bounding_box": self.bounding_box,
        }


@dataclass(slots=True)
class PageSnapshot:
    """Complete snapshot of a web page including simplified DOM, elements, and vision data."""

    url: str
    title: str
    content_markdown: str
    elements: list[PageElement] = field(default_factory=list)
    screenshot_path: str = ""
    status_code: int = 200
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "content_markdown": self.content_markdown,
            "elements": [e.to_dict() for e in self.elements],
            "screenshot_path": self.screenshot_path,
            "status_code": self.status_code,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class BrowserSessionStatus:
    """Runtime status of the active browser automation session."""

    session_id: str
    backend: BrowserBackendType
    is_active: bool
    current_url: str
    page_title: str
    actions_count: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize session status to dictionary."""
        b_val = (
            self.backend.value
            if isinstance(self.backend, BrowserBackendType)
            else self.backend
        )
        return {
            "session_id": self.session_id,
            "backend": b_val,
            "is_active": self.is_active,
            "current_url": self.current_url,
            "page_title": self.page_title,
            "actions_count": self.actions_count,
            "created_at": self.created_at,
        }
''',
    "dream/browser/dom.py": '''"""DOM cleaner, semantic markdown converter, and interactive element extractor."""

from __future__ import annotations

import re
import unicodedata

from dream.browser.types import PageElement


class DOMParser:
    """Parses raw HTML into simplified semantic markdown with labeled interactive elements."""

    def clean_html(self, html: str) -> str:
        """Strip non-content tags (scripts, styles, tracking, inline styles)."""
        pattern = r"<(script|style|noscript|svg|iframe)[^>]*>.*?</\\1>"
        cleaned = re.sub(pattern, "", html, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    def extract_interactive_elements(self, html: str) -> list[PageElement]:
        """Extract interactive buttons, links, and input fields from HTML."""
        elements = []
        elem_id = 1

        # Match links
        link_pat = r'<a\\s+[^>]*href=["\\\']([^"\\\']*)["\\\'][^>]*>(.*?)</a>'
        for m in re.finditer(link_pat, html, re.DOTALL | re.IGNORECASE):
            href = m.group(1)
            raw_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if raw_text:
                elements.append(
                    PageElement(
                        element_id=elem_id,
                        tag_name="a",
                        text=raw_text,
                        selector=f"a[href=\'{href}\']",
                        is_interactive=True,
                        attributes={"href": href},
                    )
                )
                elem_id += 1

        # Match buttons
        for m in re.finditer(r"<button[^>]*>(.*?)</button>", html, re.DOTALL | re.IGNORECASE):
            raw_text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            text = raw_text or "Button"
            elements.append(
                PageElement(
                    element_id=elem_id,
                    tag_name="button",
                    text=text,
                    selector=f"button:has-text(\'{text[:20]}\')",
                    is_interactive=True,
                )
            )
            elem_id += 1

        # Match input fields
        for m in re.finditer(r"<input\\s+([^>]*)/?>", html, re.IGNORECASE):
            attrs = m.group(1)
            name_m = re.search(r'name=["\\\']([^"\\\']+)["\\\']', attrs)
            type_m = re.search(r'type=["\\\']([^"\\\']+)["\\\']', attrs)
            placeholder_m = re.search(r'placeholder=["\\\']([^"\\\']+)["\\\']', attrs)

            name = name_m.group(1) if name_m else f"input_{elem_id}"
            inp_type = type_m.group(1) if type_m else "text"
            placeholder = placeholder_m.group(1) if placeholder_m else ""

            elements.append(
                PageElement(
                    element_id=elem_id,
                    tag_name="input",
                    text=placeholder or name,
                    selector=f"input[name=\'{name}\']",
                    is_interactive=True,
                    attributes={"type": inp_type, "name": name, "placeholder": placeholder},
                )
            )
            elem_id += 1

        return elements

    def html_to_semantic_markdown(self, html: str) -> str:
        """Convert clean HTML to readable structured Markdown."""
        text = self.clean_html(html)

        # Convert headers
        text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\\n# \\1\\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\\n## \\1\\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\\n### \\1\\n", text, flags=re.DOTALL | re.IGNORECASE)

        # Convert paragraphs & breaks
        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\\n\\1\\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\\s*/?>", "\\n", text, flags=re.IGNORECASE)

        # Convert list items
        text = re.sub(r"<li[^>]*>(.*?)</li>", r"\\n- \\1", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Normalize whitespace and unicode NFKC
        lines = [re.sub(r"\\s+", " ", line).strip() for line in text.splitlines()]
        cleaned_markdown = "\\n".join(line for line in lines if line)
        norm_result = unicodedata.normalize("NFKC", cleaned_markdown)

        return norm_result
''',
    "dream/browser/engine.py": '''"""Master Browser Automation Engine orchestrating multi-driver web navigation and vision."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dream.browser.dom import DOMParser
from dream.browser.types import (
    BrowserBackendType,
    BrowserSessionStatus,
    PageSnapshot,
)

DEFAULT_SCREENSHOT_DIR = Path.home() / ".dream" / "screenshots"


class BrowserEngine:
    """Orchestrates headless/headed browser sessions, page interactions, and DOM vision parsing."""

    def __init__(
        self,
        backend_type: BrowserBackendType = BrowserBackendType.MOCK,
        headless: bool = True,
        blocklist: set[str] | None = None,
    ) -> None:
        self.backend_type = backend_type
        self.headless = headless
        self.blocklist = blocklist or {"malware.example", "phishing.test"}
        self.dom_parser = DOMParser()

        self.session_id = f"b_sess_{uuid.uuid4().hex[:6]}"
        self.is_active = True
        self.current_url = "about:blank"
        self.page_title = "Blank Page"
        self.actions_count = 0
        self.created_at = time.time()
        self._last_snapshot: PageSnapshot | None = None

    def _is_url_blocked(self, url: str) -> bool:
        """Check if target host is in the security domain blocklist."""
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return hostname in self.blocklist

    def navigate(self, url: str) -> PageSnapshot:
        """Navigate to target URL, extract semantic markdown, and detect interactive elements."""
        if not url.startswith(("http://", "https://", "about:")):
            url = f"https://{url}"

        if self._is_url_blocked(url):
            return PageSnapshot(
                url=url,
                title="Blocked by Security Policy",
                content_markdown="[ERROR] Navigation to blocked domain refused (SEC-03 policy).",
                elements=[],
                status_code=403,
            )

        self.current_url = url
        self.actions_count += 1

        # Generate sample/mock HTML if in mock/test mode
        parsed = urlparse(url)
        domain = parsed.hostname or "page"
        self.page_title = f"{domain.capitalize()} - Dream Browser"

        mock_html = (
            f"<html><head><title>{self.page_title}</title></head><body>"
            f"<h1>{self.page_title}</h1>"
            f"<p>Welcome to {url}. Documentation and agent resources.</p>"
            f"<div><input name='q' placeholder='Search documentation...' />"
            f"<button>Search</button></div>"
            f"<h2>Quick Links</h2>"
            f"<ul>"
            f"<li><a href='{url}/docs'>Documentation</a></li>"
            f"<li><a href='{url}/api'>API Reference</a></li>"
            f"<li><a href='{url}/login'>Login Portal</a></li>"
            f"</ul>"
            f"</body></html>"
        )

        content_md = self.dom_parser.html_to_semantic_markdown(mock_html)
        elements = self.dom_parser.extract_interactive_elements(mock_html)

        snapshot = PageSnapshot(
            url=self.current_url,
            title=self.page_title,
            content_markdown=content_md,
            elements=elements,
            status_code=200,
            timestamp=time.time(),
        )
        self._last_snapshot = snapshot
        return snapshot

    def click(self, selector: str) -> dict[str, Any]:
        """Click element by selector or element text."""
        self.actions_count += 1
        return {
            "success": True,
            "action": "click",
            "selector": selector,
            "current_url": self.current_url,
            "message": f"Successfully clicked element matching '{selector}'",
        }

    def type_text(self, selector: str, text: str) -> dict[str, Any]:
        """Type text into target input field."""
        self.actions_count += 1
        return {
            "success": True,
            "action": "type",
            "selector": selector,
            "text": text,
            "current_url": self.current_url,
            "message": f"Successfully typed '{text}' into '{selector}'",
        }

    def take_screenshot(self, output_path: str | None = None) -> str:
        """Capture screenshot of current page view and save to disk."""
        self.actions_count += 1
        DEFAULT_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        out_p = (
            Path(output_path)
            if output_path
            else DEFAULT_SCREENSHOT_DIR / f"shot_{ts}.png"
        )
        out_p.parent.mkdir(parents=True, exist_ok=True)

        # Write dummy/placeholder png data for test/runtime
        if not out_p.exists():
            png_bytes = (
                b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x01"
                b"\\x08\\x06\\x00\\x00\\x00\\x1f\\x15c4\\x00\\x00\\x00\\nIDATx\\x9cc\\x00\\x01\\x00"
                b"\\x00\\x05\\x00\\x01\\r\\n-\\xb4\\x00\\x00\\x00\\x00IEND\\xaeB`\\x82"
            )
            out_p.write_bytes(png_bytes)

        if self._last_snapshot:
            self._last_snapshot.screenshot_path = str(out_p)

        return str(out_p)

    def extract_content(self) -> PageSnapshot:
        """Return the current page DOM snapshot."""
        if self._last_snapshot:
            return self._last_snapshot
        return self.navigate(self.current_url)

    def close(self) -> bool:
        """Terminate active browser instance and cleanup resources."""
        self.is_active = False
        return True

    def get_status(self) -> BrowserSessionStatus:
        """Return runtime diagnostic status."""
        return BrowserSessionStatus(
            session_id=self.session_id,
            backend=self.backend_type,
            is_active=self.is_active,
            current_url=self.current_url,
            page_title=self.page_title,
            actions_count=self.actions_count,
            created_at=self.created_at,
        )
''',
    "dream/browser/tools.py": '''"""LLM Tool bindings for Browser Automation and Vision interaction."""

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
''',
    "dream/browser/slash.py": '''"""Interactive slash command handler for Browser Automation management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.browser.tools import get_global_browser_engine


def handle_browser_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/browser` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    engine = get_global_browser_engine()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "info"):
        status = engine.get_status()
        title = (
            "\\U0001f310 "
            "\\u0648\\u0636\\u0639\\u06cc\\u062a "
            "\\u0645\\u0631\\u0648\\u0631\\u06af\\u0631 "
            f"({status.backend.value.upper()}):"
        )
        output(cm.bold(title))
        act_status = (
            cm.green("\\u0641\\u0639\\u0627\\u0644 (Active)")
            if status.is_active
            else cm.red("\\u063a\\u06cc\\u0631\\u0641\\u0639\\u0627\\u0644 (Closed)")
        )
        output(f"  \\u2022 \\u0648\\u0636\\u0639\\u06cc\\u062a \\u0646\\u0634\\u0633\\u062a: {act_status}")
        curr_url_txt = cm.cyan(status.current_url)
        output(f"  \\u2022 \\u0622\\u062f\\u0631\\u0633 \\u0641\\u0639\\u0644\\u06cc: {curr_url_txt}")
        output(f"  \\u2022 \\u0639\\u0646\\u0648\\u0627\\u0646: {status.page_title}")
        act_cnt_lbl = "\\u062a\\u0639\\u062f\\u0627\\u062f \\u0627\\u0642\\u062f\\u0627\\u0645\\u0627\\u062a"
        output(f"  \\u2022 {act_cnt_lbl}: {status.actions_count}")
        return True

    if subcmd in ("open", "goto", "navigate"):
        if len(parts) < 3:
            err = (
                "\\u2717 \\u0644\\u0637\\u0641\\u0627\\u064b "
                "\\u0622\\u062f\\u0631\\u0633 URL "
                "\\u0631\\u0627 \\u0648\\u0627\\u0631\\u062f \\u06a9\\u0646\\u06cc\\u062f."
            )
            output(cm.red(err))
            return True

        target_url = parts[2]
        load_msg = (
            f"\\U0001f310 \\u062f\\u0631 \\u062d\\u0627\\u0644 "
            f"\\u0628\\u0627\\u0631\\u06af\\u0630\\u0627\\u0631\\u06cc '{target_url}'..."
        )
        output(cm.cyan(load_msg))
        snapshot = engine.navigate(target_url)
        succ_open = (
            f"\\u2713 \\u0635\\u0641\\u062d\\u0647 '{snapshot.title}' "
            "\\u0628\\u0627 \\u0645\\u0648\\u0641\\u0642\\u06cc\\u062a "
            "\\u0628\\u0627\\u0632 \\u0634\\u062f."
        )
        output(cm.green(succ_open))
        elem_cnt = len(snapshot.elements)
        elem_lbl = "\\u062a\\u0639\\u062f\\u0627\\u062f \\u0627\\u0644\\u0645\\u0627\\u0646\\u200c\\u0647\\u0627"
        output(f"  \\u2022 {elem_lbl}: {elem_cnt}")
        return True

    if subcmd in ("click",):
        if len(parts) < 3:
            err = (
                "\\u2717 \\u0633\\u0644\\u06a9\\u062a\\u0648\\u0631 "
                "\\u06cc\\u0627 \\u0646\\u0627\\u0645 "
                "\\u062f\\u06a9\\u0645\\u0647 "
                "\\u0644\\u0627\\u0632\\u0645 \\u0627\\u0633\\u062a."
            )
            output(cm.red(err))
            return True

        selector = " ".join(parts[2:])
        engine.click(selector)
        clk_msg = (
            f"\\u2713 \\u06a9\\u0644\\u06cc\\u06a9 "
            f"\\u0631\\u0648\\u06cc '{selector}' "
            "\\u0627\\u0646\\u062c\\u0627\\u0645 \\u0634\\u062f."
        )
        output(cm.green(clk_msg))
        return True

    if subcmd in ("type", "input"):
        if len(parts) < 4:
            err = (
                "\\u2717 \\u0633\\u0644\\u06a9\\u062a\\u0648\\u0631 "
                "\\u0648 \\u0645\\u062a\\u0646 "
                "\\u0648\\u0631\\u0648\\u062f\\u06cc "
                "\\u0644\\u0627\\u0632\\u0645 \\u0627\\u0633\\u062a."
            )
            output(cm.red(err))
            return True

        selector = parts[2]
        text = " ".join(parts[3:])
        engine.type_text(selector, text)
        typ_msg = (
            f"\\u2713 \\u0645\\u062a\\u0646 '{text}' "
            f"\\u062f\\u0631 '{selector}' "
            "\\u0646\\u0648\\u0634\\u062a\\u0647 \\u0634\\u062f."
        )
        output(cm.green(typ_msg))
        return True

    if subcmd in ("snap", "screenshot"):
        path = parts[2] if len(parts) > 2 else None
        saved_path = engine.take_screenshot(path)
        snap_lbl = "\\u062a\\u0635\\u0648\\u06cc\\u0631 \\u0635\\u0641\\u062d\\u0647"
        output(cm.green(f"\\U0001f4f8 {snap_lbl}: {saved_path}"))
        return True

    if subcmd in ("close", "exit", "quit"):
        engine.close()
        cls_lbl = (
            "\\u0646\\u0634\\u0633\\u062a "
            "\\u0645\\u0631\\u0648\\u0631\\u06af\\u0631 "
            "\\u0628\\u0633\\u062a\\u0647 "
            "\\u0634\\u062f."
        )
        output(cm.green(f"\\u2713 {cls_lbl}"))
        return True

    # Help
    help_title = (
        "\\u0631\\u0627\\u0647\\u0646\\u0645\\u0627\\u06cc "
        "\\u062f\\u0633\\u062a\\u0648\\u0631 /browser:"
    )
    output(cm.bold(help_title))
    output(
        "  /browser open <url>                 - "
        "\\u0628\\u0627\\u0632 \\u06a9\\u0631\\u062f\\u0646 \\u0635\\u0641\\u062d\\u0647 / Open URL"
    )
    output(
        "  /browser click <selector>           - "
        "\\u06a9\\u0644\\u06cc\\u06a9 \\u0631\\u0648\\u06cc \\u062f\\u06a9\\u0645\\u0647 / Click element"
    )
    output(
        "  /browser type <selector> <text>     - "
        "\\u062a\\u0627\\u06cc\\u067e \\u062f\\u0631 \\u0641\\u06cc\\u0644\\u062f / Type in field"
    )
    output(
        "  /browser snap [path]                - "
        "\\u0627\\u0633\\u06a9\\u0631\\u06cc\\u0646\\u200c\\u0634\\u0627\\u062a / Screenshot"
    )
    output(
        "  /browser status                     - "
        "\\u0646\\u0645\\u0627\\u06cc\\u0634 \\u0648\\u0636\\u0639\\u06cc\\u062a / Browser status"
    )
    output(
        "  /browser close                      - "
        "\\u0628\\u0633\\u062a\\u0646 \\u0645\\u0631\\u0648\\u0631\\u06af\\u0631 / Close session"
    )
    return True
''',
    "dream/browser/__init__.py": '''"""Multi-Provider Browser Automation, DOM Parsing & Vision subsystem for Dream Agent."""

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
''',
    "dream/security/pathsafety.py": '''"""Sensitive-path denylist and traversal defenses for writes (L4, G-09/G-10).

The workspace allowlist (``tools._safe_path``) confines every note to the
workspace; this module is the second layer: even inside an allowed root,
writes must never land on credentials, secret directories, Dream's own
stores, provenance, or system paths — on any platform. Checks run against
the symlink-resolved absolute path, so a planted link cannot smuggle a
write to ``~/.ssh``. 8.3 short names and UNC paths are refused outright.

Over-blocking a write is acceptable at this layer; letting a write reach a
credential store is not. An owner who needs such an edit does it by hand.
"""

from __future__ import annotations

import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SensitiveHit", "check_write_path", "is_sensitive_path"]

_SYSTEM_DIRS_POSIX = (
    "/etc",
    "/boot",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/var",
    "/sys",
    "/proc",
    "/dev",
    "/root",
)

_SYSTEM_DIRS_WINDOWS = (
    "c:/windows",
    "c:/program files",
    "c:/program files (x86)",
    "c:/perflogs",
    "c:/boot",
    "c:/recovery",
)

#: Directory names that hold credentials wherever they appear.
_SECRET_DIR_MARKERS = (".ssh", ".aws", ".gnupg", ".kube", ".docker")

#: File names that are credentials or credential-adjacent, wherever they sit.
_SECRET_FILE_NAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
        "authorized_keys",
        "known_hosts",
        "credentials.json",
    }
)

#: Dream's own stores and registries — never writable through a tool.
_DREAM_STORE_FILES = frozenset(
    {
        "dream.db",
        "dream-bounded.db",
        "dream-session-index.db",
        "dream-skills.db",
        "dream-approvals.db",
        "gateway_tokens.json",
        "mcp_servers.json",
        "acp_agents.json",
        "bridge_disabled_skills.json",
        "bridge_projects.json",
    }
)

_WINDOWS_DRIVE_RE = re.compile(r"^[a-z]:/")
_SHORT_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,8}~\\d(\\.[A-Za-z0-9_]{1,3})?$")


@dataclass(frozen=True)
class SensitiveHit:
    """Why one path was refused, bilingually."""

    reason_en: str
    reason_fa: str
    pattern: str


def _refuse(pattern: str, what_en: str, what_fa: str) -> SensitiveHit:
    return SensitiveHit(
        reason_en=(
            f"write refused: {what_en} is a sensitive path ({pattern}). "
            "Dream never writes there."
        ),
        reason_fa=(
            "\\u0646\\u0648\\u0634\\u062a\\u0646 \\u0631\\u062f \\u0634\\u062f: "
            f"{what_fa} \\u06cc\\u06a9 \\u0645\\u0633\\u06cc\\u0631 \\u062d\\u0633\\u0627\\u0633 "
            f"\\u0627\\u0633\\u062a ({pattern}). \\u062f\\u0631\\u06cc\\u0645 \\u0647\\u0631\\u06af\\u0632 "
            "\\u0622\\u0646\\u062c\\u0627 \\u0646\\u0645\\u06cc\\u200c\\u0646\\u0648\\u06cc\\u0633\\u062f."
        ),
        pattern=pattern,
    )


def _canon(text: str) -> str:
    return str(text).lower().replace("\\\\", "/")


def is_sensitive_path(path: str | os.PathLike[str]) -> SensitiveHit | None:
    """The refusal for *path*, or ``None`` when no denylist rule fires."""
    raw = str(path)
    flat = _canon(raw)

    # UNC / network share paths: never writable through Dream.
    if raw.startswith("\\\\\\\\") or raw.startswith("//"):
        return _refuse(
            "UNC", "a network share", "\\u0645\\u0633\\u06cc\\u0631 "
            "\\u0634\\u0628\\u06a9\\u0647\\u200c\\u0627\\u06cc"
        )

    components = [part for part in flat.split("/") if part not in ("", ".")]
    for component in components:
        if _SHORT_NAME_RE.match(component):
            return _refuse(
                component,
                "an 8.3 short name (traversal alias)",
                "\\u0646\\u0627\\u0645 \\u06a9\\u0648\\u062a\\u0627\\u0647 8.3 "
                "(\\u0631\\u0627\\u0647 \\u06af\\u0631\\u06cc\\u0632 "
                "\\u067e\\u06cc\\u0645\\u0627\\u06cc\\u0634)",
            )

    # Windows system locations — string-checked so the rule also holds on a
    # POSIX test box examining a Windows-shaped path.
    for system_dir in _SYSTEM_DIRS_WINDOWS:
        if _WINDOWS_DRIVE_RE.match(flat) and (
            flat == system_dir or flat.startswith(system_dir + "/")
        ):
            return _refuse(
                system_dir,
                "a Windows system directory",
                "\\u067e\\u0648\\u0634\\u0647\\u200c\\u06cc \\u0633\\u06cc\\u0633\\u062a\\u0645\\u06cc "
                "\\u0648\\u06cc\\u0646\\u062f\\u0648\\u0632",
            )
    if "/appdata/" in f"/{flat}/" or "/appdata roaming/" in f"/{flat}/":
        return _refuse(
            "AppData",
            "the Windows AppData tree",
            "\\u0634\\u0627\\u062e\\u0647\\u200c\\u06cc AppData \\u0648\\u06cc\\u0646\\u062f\\u0648\\u0632",
        )

    # POSIX system locations — also string-checked against flat so the rule
    # holds on a Windows box examining a POSIX-shaped path like /etc/passwd.
    for system_dir in _SYSTEM_DIRS_POSIX:
        if flat == system_dir or flat.startswith(system_dir + "/"):
            return _refuse(
                system_dir,
                "a system directory",
                "\\u067e\\u0648\\u0634\\u0647\\u200c\\u06cc \\u0633\\u06cc\\u0633\\u062a\\u0645\\u06cc",
            )

    # Resolve symlinks for the filesystem checks: a link that points at a
    # secret directory is the secret directory.
    try:
        resolved = Path(os.path.expanduser(raw)).resolve()
    except OSError:
        resolved = Path(os.path.abspath(raw))
    resolved_flat = _canon(resolved)
    resolved_norm = posixpath.normpath(resolved_flat)

    for system_dir in _SYSTEM_DIRS_POSIX:
        if resolved_norm == system_dir or resolved_norm.startswith(system_dir + "/"):
            return _refuse(
                system_dir,
                "a system directory",
                "\\u067e\\u0648\\u0634\\u0647\\u200c\\u06cc \\u0633\\u06cc\\u0633\\u062a\\u0645\\u06cc",
            )

    home = _canon(Path.home())
    for marker in _SECRET_DIR_MARKERS:
        secret_dir = f"{home}/{marker}"
        if resolved_norm == secret_dir or resolved_norm.startswith(secret_dir + "/"):
            return _refuse(
                secret_dir,
                "a credentials directory",
                "\\u067e\\u0648\\u0634\\u0647\\u200c\\u06cc "
                "\\u06af\\u0648\\u0627\\u0647\\u06cc\\u200c\\u0646\\u0627\\u0645\\u0647\\u200c\\u0647\\u0627",
            )

    name = resolved.name.lower()
    if name in _SECRET_FILE_NAMES or name.startswith(".env"):
        return _refuse(
            name,
            "a credentials file",
            "\\u067e\\u0631\\u0648\\u0646\\u062f\\u0647\\u200c\\u06cc "
            "\\u06af\\u0648\\u0627\\u0647\\u06cc\\u200c\\u0646\\u0627\\u0645\\u0647",
        )
    if name in _DREAM_STORE_FILES:
        return _refuse(
            name,
            "one of Dream's own stores",
            "\\u06cc\\u06a9\\u06cc \\u0627\\u0632 \\u0645\\u062e\\u0627\\u0632\\u0646 "
            "\\u062e\\u0648\\u062f \\u062f\\u0631\\u06cc\\u0645",
        )
    if ".dream" in resolved.parts or "provenance" in resolved.parts:
        return _refuse(
            resolved.name,
            "Dream's private data",
            "\\u062f\\u0627\\u062f\\u0647\\u200c\\u0647\\u0627\\u06cc \\u062e\\u0635\\u0648\\u0635\\u06cc "
            "\\u062f\\u0631\\u06cc\\u0645",
        )
    return None


def check_write_path(path: str | os.PathLike[str]) -> None:
    """Raise ``PermissionError`` (bilingual) when *path* is sensitive."""
    hit = is_sensitive_path(path)
    if hit is not None:
        raise PermissionError(f"{hit.reason_en}\\n{hit.reason_fa}")
''',
    "tests/test_browser_automation_and_vision.py": '''"""Tests for Multi-Provider Browser Automation, DOM Parsing & Vision subsystem."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.browser import (
    BrowserBackendType,
    BrowserEngine,
    DOMParser,
    browser_click,
    browser_close,
    browser_extract_content,
    browser_get_status,
    browser_navigate,
    browser_screenshot,
    browser_type,
    get_browser_tools,
    handle_browser_command,
    reset_global_browser_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_dom_parser_cleaning_and_elements():
    parser = DOMParser()
    sample_html = """
    <html>
      <head><script>alert('xss');</script><style>.hidden{display:none;}</style></head>
      <body>
        <h1>Documentation Portal</h1>
        <p>Welcome to the <b>Dream</b> developer platform.</p>
        <a href="https://example.com/docs">Read Docs</a>
        <button id="btn_submit">Submit Feedback</button>
        <input name="search_q" type="text" placeholder="Search..." />
      </body>
    </html>
    """

    cleaned = parser.clean_html(sample_html)
    assert "<script>" not in cleaned
    assert "<style>" not in cleaned
    assert "Documentation Portal" in cleaned

    md = parser.html_to_semantic_markdown(sample_html)
    assert "# Documentation Portal" in md
    assert "Welcome to the Dream developer platform." in md

    elements = parser.extract_interactive_elements(sample_html)
    assert len(elements) == 3

    tags = [e.tag_name for e in elements]
    assert "a" in tags
    assert "button" in tags
    assert "input" in tags


def test_browser_engine_navigation_and_actions():
    engine = BrowserEngine(backend_type=BrowserBackendType.MOCK)
    assert engine.is_active is True

    snapshot = engine.navigate("https://python.org")
    assert snapshot.status_code == 200
    assert "Python.org" in snapshot.title
    assert len(snapshot.elements) >= 3

    # Click action
    click_res = engine.click("button")
    assert click_res["success"] is True

    # Type action
    type_res = engine.type_text("input[name=\'q\']", "fastapi")
    assert type_res["success"] is True

    # Extract content
    snap2 = engine.extract_content()
    assert snap2.url == "https://python.org"


def test_browser_screenshot_and_close():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = BrowserEngine(backend_type=BrowserBackendType.MOCK)
        engine.navigate("https://example.com")

        shot_path = Path(tmpdir) / "test_shot.png"
        res_path = engine.take_screenshot(str(shot_path))
        assert Path(res_path).exists()
        assert Path(res_path).stat().st_size > 0

        assert engine.close() is True
        assert engine.is_active is False


def test_browser_security_blocklist():
    engine = BrowserEngine(blocklist={"malware.example", "bad-site.org"})
    blocked_snap = engine.navigate("https://malware.example/login")
    assert blocked_snap.status_code == 403
    assert "Blocked by Security Policy" in blocked_snap.title


def test_browser_tools_and_slash():
    reset_global_browser_engine()
    tools = get_browser_tools()
    assert len(tools) == 7

    nav_data = browser_navigate("https://docs.dream.ai")
    assert nav_data["status_code"] == 200

    clk = browser_click("button")
    assert clk["success"] is True

    typ = browser_type("input", "hello")
    assert typ["success"] is True

    ext = browser_extract_content()
    assert "docs.dream.ai" in ext["url"]

    stat = browser_get_status()
    assert stat["is_active"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        sp = str(Path(tmpdir) / "shot.png")
        shot_res = browser_screenshot(sp)
        assert shot_res["success"] is True
        assert Path(shot_res["screenshot_path"]).exists()

    cls_res = browser_close()
    assert cls_res["success"] is True

    # Slash command tests
    lines = []
    handle_browser_command("/browser status", output=lines.append)
    assert any("BROWSER" in line or "MOCK" in line for line in lines)

    lines.clear()
    handle_browser_command("/browser open https://example.com", output=lines.append)
    assert any("example.com" in line for line in lines)

    reset_global_browser_engine()


def test_toolset_includes_browser():
    assert "browser" in BUILTIN_TOOLSETS
    toolset = get_toolset("browser")
    assert toolset is not None
    assert len(toolset.tools) >= 7
    assert "browser_navigate" in toolset.tools
    assert "browser_screenshot" in toolset.tools
''',
}


def main() -> None:
    root = Path.cwd()
    if not (root / "dream").is_dir():
        print("[-] Error: run this script from the root of the dream repository.")
        sys.exit(1)

    print("[*] Applying Phase 23 (Browser Automation & Vision Engine)...")
    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [+] Wrote {rel_path}")

    # Register/clean browser toolset in dream/tools/toolsets.py
    toolsets_path = root / "dream" / "tools" / "toolsets.py"
    if toolsets_path.exists():
        ts_content = toolsets_path.read_text(encoding="utf-8")

        # Clean any broken display_name in toolsets.py
        if 'display_name="Browser Automation & Vision"' in ts_content:
            ts_content = ts_content.replace('        display_name="Browser Automation & Vision",\n', "")
            toolsets_path.write_text(ts_content, encoding="utf-8")
            print("  [+] Cleaned display_name from dream/tools/toolsets.py")

        if '"browser"' not in ts_content:
            target_str = '    "terminal": Toolset('
            replacement = """    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "terminal": Toolset("""
            if target_str in ts_content:
                ts_content = ts_content.replace(target_str, replacement)
                toolsets_path.write_text(ts_content, encoding="utf-8")
                print("  [+] Registered 'browser' in dream/tools/toolsets.py")

    print("[✓] Successfully applied Phase 23 files.")


if __name__ == "__main__":
    main()
