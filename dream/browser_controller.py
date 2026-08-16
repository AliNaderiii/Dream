"""Chrome Browser Control — drive a real or isolated Chrome instance via CDP.

Provides the :class:`BrowserController` class that can attach to the user's
existing Chrome (with ``--remote-debugging-port``) or launch a fresh isolated
instance for web automation tasks.

Uses Playwright under the hood for reliable cross-platform browser control.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class PageContent:
    """Structured content of a web page."""

    url: str = ""
    title: str = ""
    text: str = ""
    html: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    screenshot_path: str | None = None


@dataclass
class BrowserSession:
    """State for one browser session (approval tracking)."""

    id: str
    url: str
    purpose: str
    domain: str
    status: str = "pending"  # pending | active | closed
    allowed_once: bool = False
    always_allow_domain: bool = False
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    closed_at: float | None = None


class BrowserUnavailableError(RuntimeError):
    """Raised when Chrome/Chromium is not found or cannot be started."""


class BrowserTimeoutError(RuntimeError):
    """Raised when a browser operation exceeds its timeout."""


class BrowserSecurityError(RuntimeError):
    """Raised when a security check fails (e.g. URL not approved)."""


# ---------------------------------------------------------------------------
# BrowserController
# ---------------------------------------------------------------------------


class BrowserController:
    """Control a Chrome/Chromium browser instance.

    Two modes:
    1. **Attach to existing** — Connect to a user's running Chrome with
       remote debugging enabled (preserves cookies, sessions, logins).
    2. **Launch isolated** — Start a fresh Chrome with no user profile
       (incognito-equivalent, no cookies or history).

    All browser sessions require user approval before navigation.
    Screenshots are saved locally only.
    """

    MAX_SESSION_DURATION_SECONDS = 300  # 5 minutes max per session

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._attached_to_existing: bool = False
        self._screenshot_dir: Path = Path(
            os.environ.get("DREAM_SCREENSHOT_DIR")
            or os.path.expanduser("~/.dream/screenshots")
        )
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Session approval tracking.
        self._current_session: BrowserSession | None = None
        self._approved_domains: set[str] = set()
        self._pending_approvals: dict[str, BrowserSession] = {}

        # Active page state.
        self._page_content: PageContent | None = None

    # -- lifecycle -------------------------------------------------------- #

    async def attach_existing_browser(self, port: int = 9222) -> dict[str, Any]:
        """Attach to the user's existing Chrome with remote debugging enabled.

        Args:
            port: Remote debugging port (Chrome must have been started with
                ``--remote-debugging-port=9222``).

        Returns:
            A status dict with browser info.

        Raises:
            BrowserUnavailableError: If no browser is listening on the port.
        """
        pw = await self._get_playwright()
        try:
            self._browser = await pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}"
            )
            self._attached_to_existing = True
            self._context = self._browser.contexts[0] if self._browser.contexts else None
            if not self._context:
                self._context = await self._browser.new_context()
            self._page = self._context.pages[0] if self._context.pages else None
            if not self._page:
                self._page = await self._context.new_page()
            return {
                "mode": "attached",
                "port": port,
                "contexts": len(self._browser.contexts),
                "pages": len(self._browser.contexts[0].pages) if self._browser.contexts else 0,
            }
        except Exception as exc:
            raise BrowserUnavailableError(
                f"Could not attach to Chrome on port {port}: {exc}"
            ) from exc

    async def launch_isolated_browser(self) -> dict[str, Any]:
        """Launch a fresh isolated Chrome instance (no user profile).

        Returns:
            A status dict with browser info.

        Raises:
            BrowserUnavailableError: If Chrome cannot be launched.
        """
        chrome_path = self._find_chrome()
        if not chrome_path:
            raise BrowserUnavailableError(
                "Chrome/Chromium not found. Install Chrome or set "
                "CHROME_BIN environment variable."
            )

        pw = await self._get_playwright()

        # Create a temporary user data dir that will be discarded.
        user_data_dir = tempfile.mkdtemp(prefix="dream-chrome-")

        try:
            self._browser = await pw.chromium.launch(
                executable_path=chrome_path,
                headless=False,
                args=[
                    f"--user-data-dir={user_data_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                    "--disable-sync",
                    "--disable-default-apps",
                    "--disable-background-networking",
                    "--disable-translate",
                ],
            )
            self._attached_to_existing = False
            self._context = await self._browser.new_context(
                no_viewport=False,
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = await self._context.new_page()
            return {
                "mode": "isolated",
                "user_data_dir": user_data_dir,
            }
        except Exception as exc:
            shutil.rmtree(user_data_dir, ignore_errors=True)
            raise BrowserUnavailableError(
                f"Could not launch Chrome: {exc}"
            ) from exc

    async def navigate(
        self,
        url: str,
        purpose: str = "Web browsing",
        wait_until: str = "load",
        timeout: int = 30,
    ) -> PageContent:
        """Navigate to a URL and return the page content.

        Requires user approval for each new domain or session.

        Args:
            url: The URL to navigate to.
            purpose: Description of why the agent needs to visit this page.
            wait_until: Navigation wait condition (``"load"``, ``"domcontentloaded"``,
                ``"networkidle"``).
            timeout: Navigation timeout in seconds.

        Returns:
            :class:`PageContent` with extracted page data.
        """
        if not self._page:
            raise BrowserUnavailableError(
                "No browser attached. Call attach_existing_browser() or "
                "launch_isolated_browser() first."
            )

        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise BrowserSecurityError(f"Only HTTP(S) URLs are allowed, got: {parsed.scheme}")
        if not parsed.netloc:
            raise BrowserSecurityError(f"Invalid URL (no host): {url}")

        domain = parsed.netloc.lower()
        # Strip port from domain for approval matching.
        domain_clean = domain.split(":")[0]

        # Security gate: check approval.
        session_id = f"browser-{uuid.uuid4().hex[:12]}"
        self._current_session = BrowserSession(
            id=session_id, url=url, purpose=purpose, domain=domain_clean
        )

        # Check if domain is always-approved.
        if domain_clean not in self._approved_domains:
            self._pending_approvals[session_id] = self._current_session
            raise BrowserSecurityError(
                f"Navigation to {url} requires user approval",
                # The caller should present an approval dialog and then call
                # approve_session() or deny_session().
            )

        self._current_session.status = "active"
        self._current_session.started_at = time.time()

        try:
            await asyncio.wait_for(
                self._page.goto(url, wait_until=wait_until),
                timeout=timeout,
            )
            content = await self._extract_content()
            self._page_content = content
            return content
        except asyncio.TimeoutError:
            raise BrowserTimeoutError(
                f"Navigation to {url} timed out after {timeout}s"
            )

    async def get_content(self) -> PageContent:
        """Return the content of the current page."""
        if not self._page:
            raise BrowserUnavailableError("No active page.")
        self._page_content = await self._extract_content()
        return self._page_content

    async def execute_js(self, script: str) -> Any:
        """Execute JavaScript in the context of the current page.

        Args:
            script: JavaScript code to execute.

        Returns:
            The JavaScript return value (JSON-serializable).
        """
        if not self._page:
            raise BrowserUnavailableError("No active page.")
        return await self._page.evaluate(script)

    async def fill_form(self, selector: str, value: str) -> None:
        """Fill a form field identified by CSS selector.

        Args:
            selector: CSS selector for the input element.
            value: Text to type into the field.
        """
        if not self._page:
            raise BrowserUnavailableError("No active page.")
        await self._page.fill(selector, value)

    async def click(self, selector: str) -> None:
        """Click an element identified by CSS selector.

        Args:
            selector: CSS selector for the element.
        """
        if not self._page:
            raise BrowserUnavailableError("No active page.")
        await self._page.click(selector)

    async def screenshot(self, path: str | None = None) -> Path:
        """Take a screenshot of the current page.

        Screenshots are saved locally only, in the screenshots directory.
        Full-page screenshots by default.

        Args:
            path: Optional override path for the screenshot file.

        Returns:
            Path to the saved screenshot file.
        """
        if not self._page:
            raise BrowserUnavailableError("No active page.")

        if path:
            screenshot_path = Path(path)
        else:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            screenshot_path = self._screenshot_dir / f"screenshot-{timestamp}.png"

        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await self._page.screenshot(path=str(screenshot_path), full_page=True)
        return screenshot_path

    async def get_cookies(self) -> list[dict[str, Any]]:
        """Return all cookies from the current browser context.

        Returns:
            List of cookie dicts (name, value, domain, path, etc.).
        """
        if not self._context:
            raise BrowserUnavailableError("No browser context.")
        return await self._context.cookies()

    async def close(self) -> None:
        """Close the browser and clean up resources."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._attached_to_existing = False

    # -- approval --------------------------------------------------------- #

    def request_approval(
        self, url: str, purpose: str
    ) -> BrowserSession:
        """Create an approval request for a browser navigation.

        Returns:
            A :class:`BrowserSession` with ``status="pending"``.

        The caller (UI/bridge) should present an approval dialog and call
        either :meth:`approve_session` or :meth:`deny_session`.
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower().split(":")[0]
        session_id = f"browser-{uuid.uuid4().hex[:12]}"
        session = BrowserSession(
            id=session_id, url=url, purpose=purpose, domain=domain
        )
        self._pending_approvals[session_id] = session
        return session

    def approve_session(
        self, session_id: str, always_allow: bool = False
    ) -> BrowserSession | None:
        """Approve a pending browser session.

        Args:
            session_id: The session ID from :meth:`request_approval`.
            always_allow: If ``True``, remember the domain and auto-approve
                future navigations.

        Returns:
            The updated :class:`BrowserSession`, or ``None`` if not found.
        """
        session = self._pending_approvals.get(session_id)
        if not session:
            return None
        session.status = "active"
        session.allowed_once = True
        if always_allow:
            session.always_allow_domain = True
            self._approved_domains.add(session.domain)
        self._current_session = session
        return session

    def deny_session(self, session_id: str) -> BrowserSession | None:
        """Deny a pending browser session."""
        session = self._pending_approvals.get(session_id)
        if not session:
            return None
        session.status = "closed"
        session.closed_at = time.time()
        return session

    # -- status ----------------------------------------------------------- #

    def get_status(self) -> dict[str, Any]:
        """Return the current browser controller status."""
        return {
            "attached": self._browser is not None,
            "attached_to_existing": self._attached_to_existing,
            "has_page": self._page is not None,
            "pending_approvals": len(self._pending_approvals),
            "approved_domains": sorted(self._approved_domains),
            "current_session": {
                "id": self._current_session.id,
                "url": self._current_session.url,
                "status": self._current_session.status,
                "domain": self._current_session.domain,
            }
            if self._current_session
            else None,
            "screenshot_dir": str(self._screenshot_dir),
        }

    # -- internals -------------------------------------------------------- #

    async def _get_playwright(self) -> Any:
        """Lazy-import and return the Playwright module."""
        if self._playwright is not None:
            return self._playwright
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            return self._playwright
        except ImportError:
            raise BrowserUnavailableError(
                "Playwright is not installed. Install it with: "
                "pip install playwright && playwright install chromium"
            )

    async def _extract_content(self) -> PageContent:
        """Extract structured content from the current page."""
        if not self._page:
            return PageContent()

        content = PageContent(
            url=self._page.url,
            title=await self._page.title(),
        )

        # Extract visible text.
        try:
            content.text = await self._page.evaluate(
                "() => document.body?.innerText ?? ''"
            )
        except Exception:
            content.text = ""

        # Extract HTML.
        try:
            content.html = await self._page.content()
        except Exception:
            content.html = ""

        # Extract links.
        try:
            links = await self._page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({ text: a.innerText.trim(), href: a.href }))
                    .filter(l => l.text || l.href)
                    .slice(0, 200)"""
            )
            content.links = links
        except Exception:
            content.links = []

        # Extract tables.
        try:
            tables = await self._page.evaluate(
                """() => Array.from(document.querySelectorAll('table'))
                    .map(table =>
                        Array.from(table.querySelectorAll('tr'))
                            .map(row =>
                                Array.from(row.querySelectorAll('td, th'))
                                    .map(cell => cell.innerText.trim())
                            )
                    )
                    .slice(0, 20)"""
            )
            content.tables = tables
        except Exception:
            content.tables = []

        return content

    @staticmethod
    def _find_chrome() -> str | None:
        """Find the Chrome/Chromium executable path."""
        # Check env var first.
        env_chrome = os.environ.get("CHROME_BIN") or os.environ.get("CHROME_PATH")
        if env_chrome and Path(env_chrome).exists():
            return env_chrome

        system = platform.system()
        if system == "Darwin":
            candidates = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                os.path.expanduser(
                    "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                ),
            ]
        elif system == "Windows":
            candidates = [
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                os.path.expanduser(
                    "~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"
                ),
            ]
        else:
            # Linux
            candidates = [
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ]

        for candidate in candidates:
            path = shutil.which(candidate)
            if path:
                return path

        return None


__all__ = [
    "BrowserController",
    "PageContent",
    "BrowserSession",
    "BrowserUnavailableError",
    "BrowserTimeoutError",
    "BrowserSecurityError",
]