"""Propose a public URL, fetch only after Allow once. No Chrome, no YOLO."""

from __future__ import annotations

import ipaddress
import os
import re
import threading
import uuid
from typing import Any
from urllib.parse import urlsplit

from dream import tools
from dream.browse.errors import BrowseError, BrowseSecurityError
from dream.browse.store import BrowseStore, now
from dream.security.injection import scan_text

_EXCERPT_CAP = 8_000
_URL_CAP = 2_048
_LINK_CAP = 8
_NETWORK_ON = frozenset({"1", "true", "yes", "on"})
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".corp")
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata",
        "0.0.0.0",
        "::1",
        "::",
    }
)
_LINK_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SERVICE: BrowseService | None = None
_LOCK = threading.Lock()


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def _network_on() -> bool:
    return os.environ.get("DREAM_ALLOW_NETWORK", "").strip().lower() in _NETWORK_ON


def _syntax_url(address: str) -> str:
    raw = (address or "").strip()
    if not raw or len(raw) > _URL_CAP or any(ord(ch) < 32 for ch in raw) or "\\" in raw:
        raise BrowseSecurityError(
            _bilingual(
                "url must be a public http(s) address of at most 2048 characters",
                "نشانی باید http(s) عمومی حداکثر ۲۰۴۸ نویسه باشد",
            )
        )
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise BrowseSecurityError(
            _bilingual(
                "only public http(s) URLs are allowed",
                "فقط نشانی http(s) عمومی مجاز است",
            )
        )
    if parsed.username or parsed.password:
        raise BrowseSecurityError(
            _bilingual(
                "credentials in URL are refused",
                "اعتبارنامه داخل نشانی رد است",
            )
        )
    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS or any(host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        raise BrowseSecurityError(
            _bilingual(
                "localhost and internal hosts are refused",
                "localhost و میزبان داخلی رد است",
            )
        )
    try:
        literal = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise BrowseSecurityError(
            _bilingual(
                "private and loopback addresses are refused",
                "نشانی خصوصی و loopback رد است",
            )
        )
    return raw


def _title_from(excerpt: str, url: str) -> str:
    for line in excerpt.splitlines():
        text = line.strip()
        if text and not text.startswith("[") and text.lower() != "truncated":
            return text[:120]
    host = urlsplit(url).hostname or "page"
    return host


def _links_from(excerpt: str, origin: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _LINK_RE.findall(excerpt):
        candidate = match.rstrip(").,]\"'")
        if candidate == origin or candidate in seen:
            continue
        try:
            checked = _syntax_url(candidate)
        except BrowseSecurityError:
            continue
        host = (urlsplit(checked).hostname or "").lower()
        found.append({"url": checked, "host": host})
        seen.add(candidate)
        if len(found) >= _LINK_CAP:
            break
    return found


class BrowseService:
    def __init__(self, store: BrowseStore | None = None) -> None:
        self.store = store or BrowseStore()

    def propose(self, url: str, *, yolo: bool = False) -> dict[str, Any]:
        if yolo:
            raise BrowseSecurityError(
                _bilingual(
                    "YOLO cannot open pages",
                    "YOLO نمی‌تواند صفحه باز کند",
                )
            )
        address = _syntax_url(url)
        report = scan_text(address)
        if any(finding.kind == "instruction_override" for finding in report.findings):
            raise BrowseSecurityError(
                _bilingual(
                    "url looks like a prompt injection",
                    "نشانی شبیه تزریق پرامپت است",
                )
            )
        record = {
            "draft_id": f"brw_{uuid.uuid4().hex[:12]}",
            "url": address,
            "status": "APPROVAL_PENDING",
            "yolo": False,
            "chrome_profile": False,
            "computer_use": False,
            "hosted_fetch": False,
            "excerpt": "",
            "title": urlsplit(address).hostname or "page",
            "links": [],
            "truncated": False,
            "created_at": now(),
        }
        return self.store.put(record)

    def list(self) -> dict[str, Any]:
        rows = []
        for row in self.store.list():
            item = dict(row)
            excerpt = str(item.get("excerpt") or "")
            if len(excerpt) > 240:
                item["excerpt"] = excerpt[:240]
            rows.append(item)
        return {"drafts": rows, "count": len(rows)}

    def get(self, draft_id: str) -> dict[str, Any]:
        return self.store.get(draft_id)

    def approve(self, draft_id: str, *, approved: bool = False) -> dict[str, Any]:
        if not approved:
            raise BrowseSecurityError(
                _bilingual("missing approver — refuse", "تأییدکننده نیست — رد شد")
            )
        if not _network_on():
            raise BrowseSecurityError(
                _bilingual(
                    "owner has not enabled network access",
                    "مالک دسترسی شبکه را فعال نکرده است",
                )
            )
        record = self.store.get(draft_id)
        if record.get("status") != "APPROVAL_PENDING":
            raise BrowseError(
                _bilingual(
                    "this draft is no longer pending",
                    "این پیشنویس دیگر در انتظار نیست",
                )
            )
        body = tools.read_page(record["url"])
        truncated = "[truncated" in body
        if body in {tools.NETWORK_DISABLED_MESSAGE, tools.NETWORK_REFUSAL_MESSAGE}:
            record["status"] = "refused"
            record["hosted_fetch"] = False
            record["excerpt"] = body[:_EXCERPT_CAP]
            record["title"] = "refused"
            record["links"] = []
            record["truncated"] = False
            return self.store.put(record)
        excerpt = body[:_EXCERPT_CAP]
        record["status"] = "fetched"
        record["hosted_fetch"] = True
        record["excerpt"] = excerpt
        record["title"] = _title_from(excerpt, record["url"])
        record["links"] = _links_from(excerpt, record["url"])
        record["truncated"] = truncated or len(body) > _EXCERPT_CAP
        record["chrome_profile"] = False
        record["computer_use"] = False
        record["yolo"] = False
        return self.store.put(record)

    def deny(self, draft_id: str) -> dict[str, Any]:
        record = self.store.pop(draft_id)
        return {
            "applied": False,
            "draft_id": draft_id,
            "url": record["url"],
            "status": "denied",
            "hosted_fetch": False,
            "chrome_profile": False,
            "computer_use": False,
            "yolo": False,
        }

    def follow(self, draft_id: str, url: str, *, yolo: bool = False) -> dict[str, Any]:
        parent = self.store.get(draft_id)
        if parent.get("status") != "fetched":
            raise BrowseError(
                _bilingual(
                    "only fetched pages expose followable links",
                    "فقط صفحهٔ واکشی‌شده پیوند قابل‌دنبال‌کردن دارد",
                )
            )
        allowed = {
            str(item.get("url"))
            for item in parent.get("links") or []
            if isinstance(item, dict)
        }
        if url.strip() not in allowed:
            raise BrowseSecurityError(
                _bilingual(
                    "url is not an extracted link from this page",
                    "این نشانی از پیوندهای استخراج‌شده این صفحه نیست",
                )
            )
        return self.propose(url, yolo=yolo)


def get_service() -> BrowseService:
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = BrowseService()
        return _SERVICE


def reset_service(service: BrowseService | None = None) -> BrowseService | None:
    global _SERVICE
    with _LOCK:
        _SERVICE = service
        return _SERVICE
