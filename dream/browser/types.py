"""Data types and domain models for Multi-Provider Browser Automation & Vision subsystem."""

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
