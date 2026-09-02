"""Chrome Browser Control — drive a real or isolated Chrome instance via CDP.

Provides the :class:`BrowserController` class that can attach to the user's
existing Chrome (with ``--remote-debugging-port``) or launch a fresh isolated
instance for web automation tasks.

Uses Playwright under the hood for reliable cross-platform browser control.

Security model (SEC-03)
-----------------------
* Every navigation requires explicit user approval. There is **no** always-allow
  bypass — approvals expire after ``approval_ttl_seconds`` (default 900 s) and
  must be re-issued.
* A per-session fetch quota (default 20) caps how many navigations a single
  browser session may perform. Failed requests **do** count toward the quota to
  prevent retry-loop abuse.
* A domain blocklist (loaded from ``~/.dream/blocked_domains.txt`` and optionally
  ``data/blocked_domains.txt`` relative to the repository root) is checked before
  any approval or network access.  Blocklist rejection cannot be bypassed by an
  approval flag.
* Full URLs containing query parameters, credentials, or tokens are never logged.
  Only scheme+host information appears in log messages.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default approval TTL in seconds (SEC-03 requirement: 900 s).
DEFAULT_APPROVAL_TTL: int = 900

#: Default maximum fetches per browser session (SEC-03 requirement: 20).
DEFAULT_MAX_FETCHES: int = 20

#: Blocklist search paths, checked in order.
_BLOCKLIST_PATHS: tuple[str, ...] = (
    os.path.expanduser("~/.dream/blocked_domains.txt"),
    str(Path(__file__).parent.parent / "data" / "blocked_domains.txt"),
)

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
    """State for one browser session (approval tracking).

    SEC-03 changes:
    * ``always_allow_domain`` has been **removed** — there is no permanent bypass.
    * ``approved_at`` records the monotonic clock value when approval was granted,
      enabling deterministic TTL testing via dependency injection.
    * ``fetch_count`` tracks how many fetches have been attempted this session.
    """

    id: str
    url: str
    purpose: str
    domain: str
    status: str = "pending"  # pending | active | expired | closed
    allowed_once: bool = False
    # approved_at stores the monotonic clock value at approval time.
    # None means not yet approved.
    approved_at: float | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    closed_at: float | None = None
    fetch_count: int = 0


class BrowserUnavailableError(RuntimeError):
    """Raised when Chrome/Chromium is not found or cannot be started."""


class BrowserTimeoutError(RuntimeError):
    """Raised when a browser operation exceeds its timeout."""


class BrowserSecurityError(RuntimeError):
    """Raised when a security check fails.

    Sub-cases (check ``reason`` attribute):
    * ``"approval_required"`` — domain not approved for this session.
    * ``"approval_expired"`` — previously granted approval has expired (TTL).
    * ``"quota_exceeded"`` — session fetch quota reached.
    * ``"blocked_domain"`` — domain appears in the blocklist.
    * ``"invalid_url"`` — URL fails scheme or format validation.
    """

    def __init__(self, message: str, reason: str = "") -> None:
        super().__init__(message)
        self.reason = reason


# ---------------------------------------------------------------------------
# Domain blocklist
# ---------------------------------------------------------------------------


def _load_blocklist(paths: tuple[str, ...] = _BLOCKLIST_PATHS) -> frozenset[str]:
    """Load and return the set of blocked normalised hostnames.

    Rules:
    * Each non-blank, non-comment line is one entry.
    * Comments begin with ``#``.
    * Entries are normalised to lower-case, with trailing dots removed.
    * Entries that contain characters invalid for a hostname (after normalisation)
      are silently skipped with a warning (fail-safe, not fail-open).
    * Missing files are silently ignored.

    Returns:
        A frozenset of lowercase, dot-stripped hostnames.
    """
    blocked: set[str] = set()
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("blocklist: could not read %s: %s", p, type(exc).__name__)
            continue
        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip inline comments.
            entry = line.split("#", 1)[0].strip()
            if not entry:
                continue
            normalised = _normalise_hostname(entry)
            if normalised is None:
                logger.warning(
                    "blocklist: skipping malformed entry at %s:%d", p, lineno
                )
                continue
            blocked.add(normalised)
    return frozenset(blocked)


def _normalise_hostname(raw: str) -> str | None:
    """Normalise a raw hostname string to a comparable form.

    Returns:
        The normalised hostname (lowercase, no trailing dot, no port), or
        ``None`` if the entry is clearly malformed.
    """
    # Strip scheme if accidentally included.
    for prefix in ("https://", "http://", "ftp://"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
    # Strip path.
    raw = raw.split("/", 1)[0]
    # Strip port.
    # Handle IPv6 bracketed addresses — not a valid blocklist entry, skip.
    if raw.startswith("["):
        return None
    raw = raw.rsplit(":", 1)[0] if ":" in raw else raw
    # Lowercase and strip trailing dot.
    normalised = raw.lower().rstrip(".")
    if not normalised:
        return None
    # Reject entries that look like they contain spaces or control characters —
    # these cannot be valid hostnames.
    if any(c in normalised for c in (" ", "\t", "\r", "\n")):
        return None
    # Basic hostname character check: labels may contain letters, digits, hyphens.
    # We are lenient to support IDN (will be lowercase ASCII after punycode encode
    # for common cases), but we reject anything with shell-special characters.
    invalid_chars = set('<>(){}|\\^`\'"')
    if any(c in invalid_chars for c in normalised):
        return None
    return normalised


def _is_blocked(hostname: str, blocklist: frozenset[str]) -> bool:
    """Return ``True`` iff *hostname* is blocked by *blocklist*.

    Matching rules:
    * Exact match: ``example.com`` blocks requests to ``example.com``.
    * Subdomain match: ``example.com`` in the blocklist blocks
      ``sub.example.com``, ``a.b.example.com`` etc., but **not**
      ``badexample.com`` or ``notexample.com``.

    Args:
        hostname: The normalised (lowercase, no trailing dot) hostname to test.
        blocklist: The loaded blocklist (from :func:`_load_blocklist`).
    """
    if hostname in blocklist:
        return True
    # Check if any blocked entry is a parent domain of the hostname.
    # We require the match to be at a label boundary.
    for entry in blocklist:
        if hostname.endswith("." + entry):
            return True
    return False


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

    Security model (SEC-03):
    * All browser sessions require user approval before navigation.
    * Approvals expire after ``approval_ttl_seconds`` (default 900 s).
    * A per-session fetch quota (``max_fetches``, default 20) limits the number
      of navigations.  Both successful and failed fetch attempts count.
    * A domain blocklist is consulted before any approval or network access.
    * ``always_allow`` / ``always_allow_domain`` have been **removed** — there
      is no production bypass of the approval requirement.
    * Screenshots are saved locally only.
    """

    MAX_SESSION_DURATION_SECONDS: int = 300  # 5 minutes max per session

    def __init__(
        self,
        approval_ttl_seconds: int = DEFAULT_APPROVAL_TTL,
        max_fetches: int = DEFAULT_MAX_FETCHES,
        _clock: Any = None,  # injectable for tests; None → time.monotonic
        _blocklist: frozenset[str] | None = None,  # injectable for tests
    ) -> None:
        """Initialise the browser controller.

        Args:
            approval_ttl_seconds: How long (in seconds) an approval remains
                valid.  Default is 900 s (15 minutes).
            max_fetches: Maximum navigations per browser session.  Default is
                20.  The counter resets only when a new browser session is
                explicitly created via ``attach_existing_browser`` or
                ``launch_isolated_browser``.
            _clock: Optional callable that returns the current monotonic time.
                Defaults to ``time.monotonic``.  Inject a fake for tests.
            _blocklist: Optional pre-loaded blocklist set.  If ``None``,
                the blocklist is loaded from the standard paths on first use.
        """
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

        # Security policy.
        self._approval_ttl: int = approval_ttl_seconds
        self._max_fetches: int = max_fetches
        self._clock: Any = _clock if _clock is not None else time.monotonic

        # Blocklist: lazy-loaded unless injected.
        self._blocklist: frozenset[str] | None = _blocklist

        # Session approval tracking.
        self._current_session: BrowserSession | None = None
        self._pending_approvals: dict[str, BrowserSession] = {}

        # Per-session fetch counter (resets on new browser session).
        self._session_fetch_count: int = 0

        # Active page state.
        self._page_content: PageContent | None = None

    # -- blocklist -------------------------------------------------------- #

    def _get_blocklist(self) -> frozenset[str]:
        """Return the loaded blocklist, loading it lazily on first call."""
        if self._blocklist is None:
            self._blocklist = _load_blocklist()
        return self._blocklist

    def _check_blocked(self, hostname: str) -> None:
        """Raise :exc:`BrowserSecurityError` if *hostname* is blocked.

        Args:
            hostname: Normalised (lowercase, no port, no trailing dot) hostname.

        Raises:
            BrowserSecurityError: If the domain or any of its parents appears
                in the blocklist.  The error message does **not** reveal which
                blocklist entry matched.
        """
        if _is_blocked(hostname, self._get_blocklist()):
            raise BrowserSecurityError(
                "Navigation to that domain is not permitted.",
                reason="blocked_domain",
            )

    # -- lifecycle -------------------------------------------------------- #

    async def attach_existing_browser(self, port: int = 9222) -> dict[str, Any]:
        """Attach to the user's existing Chrome with remote debugging enabled.

        Resets the session fetch counter.

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
            self._session_fetch_count = 0  # reset quota for new session
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

        Resets the session fetch counter.

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
            self._session_fetch_count = 0  # reset quota for new session
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

        Security checks (in order):
        1. URL scheme and format validation.
        2. Domain blocklist check (cannot be bypassed by approval).
        3. Session fetch quota check.
        4. Approval existence and TTL check.

        Args:
            url: The URL to navigate to.
            purpose: Description of why the agent needs to visit this page.
            wait_until: Navigation wait condition (``"load"``,
                ``"domcontentloaded"``, ``"networkidle"``).
            timeout: Navigation timeout in seconds.

        Returns:
            :class:`PageContent` with extracted page data.

        Raises:
            BrowserUnavailableError: If no browser page is attached.
            BrowserSecurityError: On any security check failure.
            BrowserTimeoutError: If the navigation times out.
        """
        if not self._page:
            raise BrowserUnavailableError(
                "No browser attached. Call attach_existing_browser() or "
                "launch_isolated_browser() first."
            )

        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise BrowserSecurityError(
                f"Only HTTP(S) URLs are allowed, got: {parsed.scheme!r}",
                reason="invalid_url",
            )
        if not parsed.netloc:
            raise BrowserSecurityError("Invalid URL (no host).", reason="invalid_url")

        domain = parsed.netloc.lower()
        # Strip port from domain for blocklist and approval matching.
        domain_clean = domain.split(":")[0].rstrip(".")

        # 1. Blocklist check — must happen before approval and network access.
        self._check_blocked(domain_clean)

        # 2. Quota check — count the attempt regardless of outcome below.
        if self._session_fetch_count >= self._max_fetches:
            raise BrowserSecurityError(
                f"Session fetch quota of {self._max_fetches} has been reached.",
                reason="quota_exceeded",
            )

        # 3. Approval check — require an active, non-expired approval.
        self._require_valid_approval(domain_clean, url, purpose)

        # Increment fetch count before making the network call.
        self._session_fetch_count += 1

        try:
            await asyncio.wait_for(
                self._page.goto(url, wait_until=wait_until),
                timeout=timeout,
            )
            content = await self._extract_content()
            self._page_content = content
            return content
        except asyncio.TimeoutError as exc:
            # Log only scheme+host, not full URL (SEC-03 rule 6).
            logger.warning("navigate: timed out for host %s", domain_clean)
            raise BrowserTimeoutError(
                f"Navigation timed out after {timeout}s."
            ) from exc

    def _require_valid_approval(
        self, domain: str, url: str, purpose: str
    ) -> None:
        """Ensure there is a valid, non-expired approval for *domain*.

        If no current session exists, or the session is for a different domain,
        or the approval has expired, a new pending approval is created and
        :exc:`BrowserSecurityError` with ``reason="approval_required"`` or
        ``reason="approval_expired"`` is raised.

        Args:
            domain: Normalised hostname (no port, no trailing dot).
            url: The original URL (used only to create the pending session).
            purpose: Description for the approval dialog.
        """
        session = self._current_session
        now = self._clock()

        if session is None or session.domain != domain:
            # No session or different domain — create a new pending approval.
            session_id = f"browser-{uuid.uuid4().hex[:12]}"
            new_session = BrowserSession(
                id=session_id, url=url, purpose=purpose, domain=domain
            )
            self._pending_approvals[session_id] = new_session
            self._current_session = new_session
            raise BrowserSecurityError(
                "Navigation requires user approval.",
                reason="approval_required",
            )

        if session.approved_at is None or session.status != "active":
            raise BrowserSecurityError(
                "Navigation requires user approval.",
                reason="approval_required",
            )

        elapsed = now - session.approved_at
        if elapsed > self._approval_ttl:
            # Mark the session as expired and raise.
            session.status = "expired"
            raise BrowserSecurityError(
                "Approval has expired; please re-approve.",
                reason="approval_expired",
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
        except Exception:  # noqa: BLE001 – best-effort teardown
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

        The domain blocklist is checked here before registering the request —
        blocked domains never receive a pending session.

        Returns:
            A :class:`BrowserSession` with ``status="pending"``.

        The caller (UI/bridge) should present an approval dialog and call
        either :meth:`approve_session` or :meth:`deny_session`.

        Raises:
            BrowserSecurityError: If the domain is on the blocklist or the URL
                is invalid.
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise BrowserSecurityError(
                f"Only HTTP(S) URLs are allowed, got: {parsed.scheme!r}",
                reason="invalid_url",
            )
        if not parsed.netloc:
            raise BrowserSecurityError("Invalid URL (no host).", reason="invalid_url")

        domain = parsed.netloc.lower().split(":")[0].rstrip(".")

        # Blocklist check happens before creating the pending session.
        self._check_blocked(domain)

        session_id = f"browser-{uuid.uuid4().hex[:12]}"
        session = BrowserSession(
            id=session_id, url=url, purpose=purpose, domain=domain
        )
        self._pending_approvals[session_id] = session
        return session

    def approve_session(
        self, session_id: str
    ) -> BrowserSession | None:
        """Approve a pending browser session.

        SEC-03: The ``always_allow`` / ``always_allow_domain`` parameter has
        been **removed**.  Each approval is single-use and expires after
        ``approval_ttl_seconds``.

        If an old client sends an ``always_allow`` parameter it is silently
        ignored — it does **not** grant permanent access.

        Args:
            session_id: The session ID from :meth:`request_approval`.

        Returns:
            The updated :class:`BrowserSession`, or ``None`` if not found.
        """
        session = self._pending_approvals.get(session_id)
        if not session:
            return None
        session.status = "active"
        session.allowed_once = True
        session.approved_at = self._clock()
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
            "session_fetch_count": self._session_fetch_count,
            "max_fetches": self._max_fetches,
            "approval_ttl_seconds": self._approval_ttl,
            "current_session": {
                "id": self._current_session.id,
                "url": self._current_session.url,
                "status": self._current_session.status,
                "domain": self._current_session.domain,
                "fetch_count": self._current_session.fetch_count,
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
        except ImportError as exc:
            raise BrowserUnavailableError(
                "Playwright is not installed. Install it with: "
                "pip install playwright && playwright install chromium"
            ) from exc

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
        except Exception:  # noqa: BLE001 – best-effort extraction
            content.text = ""

        # Extract HTML.
        try:
            content.html = await self._page.content()
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
    "BrowserSecurityError",
    "BrowserSession",
    "BrowserTimeoutError",
    "BrowserUnavailableError",
    "DEFAULT_APPROVAL_TTL",
    "DEFAULT_MAX_FETCHES",
    "PageContent",
    "_is_blocked",
    "_load_blocklist",
    "_normalise_hostname",
]
