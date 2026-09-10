"""Network and web search tools with SSRF protection, redirection checks, and caps."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dream.tools.base import tool

NETWORK_TIMEOUT_SECONDS = 10
SEARCH_RESPONSE_CAP = 100_000
PAGE_RESPONSE_CAP = 250_000
PAGE_TEXT_CAP = 200_000
_NETWORK_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})
NETWORK_DISABLED_MESSAGE = (
    "\u0645\u0627\u0644\u06a9 \u062f\u0633\u062a\u0631\u0633\u06cc "
    "\u0634\u0628\u06a9\u0647 \u0631\u0627 \u0641\u0639\u0627\u0644 "
    "\u0646\u06a9\u0631\u062f\u0647 \u0627\u0633\u062a."
)
NETWORK_REFUSAL_MESSAGE = (
    "\u0627\u0645\u06a9\u0627\u0646 \u062f\u0631\u06cc\u0627\u0641\u062a "
    "\u0627\u06cc\u0646\u062a\u0631\u0646\u062a\u06cc \u0646\u06cc\u0633\u062a."
)
NETWORK_EMPTY_MESSAGE = (
    "\u062c\u0633\u062a\u062c\u0648 \u0646\u062a\u06cc\u062c\u0647\u200c\u0627\u06cc "
    "\u0628\u0631\u0646\u06af\u0631\u062f\u0627\u0646\u062f."
)
_WIKI_HOSTS = ("fa.wikipedia.org", "en.wikipedia.org")


class _AddressRefused(ValueError):
    """An untrusted model-selected URL failed Dream's network boundary."""


def _network_enabled() -> bool:
    """Whether the owner explicitly enabled the two network tools."""
    return os.environ.get("DREAM_ALLOW_NETWORK", "").strip().lower() in _NETWORK_ENABLED_VALUES


def _validate_network_url(address: str) -> str:
    """Allow only public HTTP(S) destinations, resolving every hostname now."""
    parsed = urlsplit(address)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise _AddressRefused("unsupported URL")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise _AddressRefused("internal destination is not allowed")
    if parsed.username or parsed.password:
        raise _AddressRefused("credentials in URL are not allowed")
    try:
        literal = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise _AddressRefused("internal destination is not allowed")
        return address
    try:
        candidates = socket.getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except (OSError, ValueError) as exc:
        raise _AddressRefused("destination could not be resolved") from exc
    if not candidates:
        raise _AddressRefused("destination could not be resolved")
    for candidate in candidates:
        try:
            destination = ipaddress.ip_address(candidate[4][0])
        except ValueError as exc:
            raise _AddressRefused("destination is invalid") from exc
        # is_global excludes private, loopback, link-local, reserved,
        # multicast, and unspecified ranges — all unsuitable for a model URL.
        if not destination.is_global:
            raise _AddressRefused("internal destination is not allowed")
    return address


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    """Reapply URL validation before urllib follows each redirect target."""

    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Request | None:
        del fp, code, msg, headers
        _validate_network_url(newurl)
        return super().redirect_request(req, None, 302, "Found", {}, newurl)


def _default_open_network_request(request: Request, timeout: float) -> Any:
    """Open through the redirect validator rather than urllib's blind default."""
    return build_opener(_RestrictedRedirectHandler()).open(request, timeout=timeout)


# Tests patch this seam; production starts with the standard-library opener.
_open_network_request: Callable[[Request, float], Any] = _default_open_network_request


class _ReadableText(HTMLParser):
    """Dependency-free, conservative conversion of HTML into visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        elif tag.lower() in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def _strip_markup(value: str) -> str:
    parser = _ReadableText()
    parser.feed(value)
    parser.close()
    return parser.text()


def _read_capped(response: Any, cap: int) -> tuple[bytes, bool]:
    """Read at most *cap* bytes plus one marker byte, never an unbounded body."""
    chunks: list[bytes] = []
    remaining = cap + 1
    while remaining:
        chunk = response.read(min(8192, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    return body[:cap], len(body) > cap


def _fetch(address: str, cap: int) -> tuple[bytes, bool]:
    """Validate and fetch one public URL with hard request and response limits."""
    _validate_network_url(address)
    request = Request(address, headers={"User-Agent": "dream-assistant/0.1.0"})
    import dream.tools as _dt

    opener = getattr(_dt, "_open_network_request", _open_network_request)
    with opener(request, NETWORK_TIMEOUT_SECONDS) as response:
        # A handler validates every redirect before it is followed; geturl is
        # validated again so injected/custom openers cannot bypass the boundary.
        _validate_network_url(response.geturl())
        return _read_capped(response, cap)


def _wikipedia_topics(query: str) -> list[tuple[str, str]]:
    """Public Wikipedia opensearch hits, still SSRF-gated through _fetch."""
    encoded = urlencode(
        {
            "action": "opensearch",
            "search": query,
            "limit": "5",
            "namespace": "0",
            "format": "json",
        }
    )
    rows: list[tuple[str, str]] = []
    for host in _WIKI_HOSTS:
        try:
            body, _ = _fetch(f"https://{host}/w/api.php?{encoded}", SEARCH_RESPONSE_CAP)
            payload = json.loads(body.decode("utf-8", "replace"))
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError, _AddressRefused):
            continue
        if not isinstance(payload, list) or len(payload) < 4:
            continue
        titles, urls = payload[1], payload[3]
        if not isinstance(titles, list) or not isinstance(urls, list):
            continue
        for title, address in zip(titles, urls, strict=False):
            if not isinstance(title, str) or not isinstance(address, str):
                continue
            if not title.strip() or not address.strip():
                continue
            try:
                _validate_network_url(address)
            except _AddressRefused:
                continue
            hostname = (urlsplit(address).hostname or "").lower().rstrip(".")
            if hostname not in _WIKI_HOSTS:
                continue
            rows.append((_strip_markup(title), address))
            if len(rows) >= 4:
                return rows
    return rows


def _related_topics(value: object) -> list[tuple[str, str]]:
    """Flatten DuckDuckGo's related-topic groups into at most four safe rows."""
    results: list[tuple[str, str]] = []
    if not isinstance(value, list):
        return results
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("Topics"), list):
            results.extend(_related_topics(item["Topics"]))
        elif isinstance(item, dict):
            title, address = item.get("Text"), item.get("FirstURL")
            if isinstance(title, str) and isinstance(address, str):
                results.append((_strip_markup(title), address))
        if len(results) >= 4:
            break
    return results[:4]


@tool(risk="guarded")
def search_web(query: str) -> str:
    """Search the web for a concise answer and a few related public links.

    :param query: Search terms in the owner's language.
    """
    if not _network_enabled():
        return NETWORK_DISABLED_MESSAGE
    fetch_failed = False
    answer = ""
    topics: list[tuple[str, str]] = []
    try:
        encoded = urlencode({"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"})
        body, _ = _fetch(f"https://api.duckduckgo.com/?{encoded}", SEARCH_RESPONSE_CAP)
        payload = json.loads(body.decode("utf-8", "replace"))
        answer = _strip_markup(str(payload.get("AbstractText", ""))).strip()
        topics = _related_topics(payload.get("RelatedTopics"))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, _AddressRefused):
        fetch_failed = True
    if not answer and not topics:
        wiki = _wikipedia_topics(query)
        if wiki:
            topics = wiki
        elif fetch_failed:
            return NETWORK_REFUSAL_MESSAGE
        else:
            return NETWORK_EMPTY_MESSAGE
    lines = [answer] if answer else []
    lines.extend(f"- {title}: {address}" for title, address in topics)
    from dream.security.injection import guard_untrusted

    # L5 (SEC Stage D): web extraction crosses into context only scanned.
    return guard_untrusted("\n".join(lines), source="web:search")


@tool(risk="guarded")
def read_page(address: str) -> str:
    """Read a public web page as plain text, with a stated truncation cap.

    :param address: Public HTTP or HTTPS address to read.
    """
    if not _network_enabled():
        return NETWORK_DISABLED_MESSAGE
    try:
        body, response_truncated = _fetch(address, PAGE_RESPONSE_CAP)
        text = _strip_markup(body.decode("utf-8", "replace"))
        text_truncated = len(text) > PAGE_TEXT_CAP
        if text_truncated:
            text = text[:PAGE_TEXT_CAP]
        if not text:
            return NETWORK_REFUSAL_MESSAGE
        from dream.security.injection import guard_untrusted

        # L5 (SEC Stage D): web extraction crosses into context only scanned.
        text = guard_untrusted(text, source=f"web:{address}")
        if response_truncated or text_truncated:
            return f"{text}\n\n[truncated at {PAGE_TEXT_CAP} characters]"
        return text
    except (OSError, ValueError, UnicodeError, _AddressRefused):
        return NETWORK_REFUSAL_MESSAGE
