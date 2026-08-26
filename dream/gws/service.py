"""Read-only Gmail, Calendar, and Drive. Writes are refused in this cut."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from dream.gws.errors import GwsSecurityError
from dream.gws.http import request_json
from dream.gws.oauth import GoogleOAuth
from dream.model_providers import KeychainCredentialStore
from dream.security.injection import guard_untrusted

_NETWORK_ON = frozenset({"1", "true", "yes", "on"})
_SERVICE: GoogleWorkspaceService | None = None


def _network_enabled() -> bool:
    return os.environ.get("DREAM_ALLOW_NETWORK", "").strip().lower() in _NETWORK_ON


def _bilingual(en: str, fa: str) -> str:
    return f"{en} / {fa}"


class GoogleWorkspaceService:
    """Owner-authorized Google Workspace reads."""

    def __init__(
        self,
        credentials: KeychainCredentialStore | None = None,
        opener: Any = None,
    ) -> None:
        self.oauth = GoogleOAuth(credentials=credentials, opener=opener)
        self._opener = opener or urlopen

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.oauth.connected(),
            "network": _network_enabled(),
            "redirect_uri": "http://127.0.0.1:17463/callback",
            "scopes": [
                "gmail.readonly",
                "calendar.readonly",
                "drive.readonly",
            ],
            "writes": False,
        }

    def oauth_begin(self) -> dict[str, str]:
        self._require_network()
        return self.oauth.begin()

    def oauth_complete(self, state: str, code: str) -> dict[str, Any]:
        self._require_network()
        return self.oauth.complete(state, code)

    def disconnect(self) -> dict[str, bool]:
        return self.oauth.disconnect()

    def gmail_list(self, max_results: int = 5) -> str:
        self._require_network()
        token = self.oauth.token()
        limit = _clamp(max_results)
        query = urlencode({"maxResults": str(limit)})
        payload = request_json(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages?{query}",
            token=token,
            opener=self._opener,
        )
        ids = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        lines = [f"gmail messages: {len(ids)}"]
        for row in ids[:limit]:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                lines.append(f"- {row['id']}")
        return guard_untrusted("\n".join(lines), source="gws:gmail")

    def calendar_list(self, max_results: int = 5) -> str:
        self._require_network()
        token = self.oauth.token()
        limit = _clamp(max_results)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = urlencode(
            {
                "maxResults": str(limit),
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": now,
            }
        )
        payload = request_json(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{query}",
            token=token,
            opener=self._opener,
        )
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        lines = [f"calendar events: {len(items)}"]
        for row in items[:limit]:
            if not isinstance(row, dict):
                continue
            summary = row.get("summary") if isinstance(row.get("summary"), str) else "(no title)"
            start = row.get("start") if isinstance(row.get("start"), dict) else {}
            when = start.get("dateTime") or start.get("date") or ""
            lines.append(f"- {when} {summary}")
        return guard_untrusted("\n".join(lines), source="gws:calendar")

    def drive_list(self, max_results: int = 5) -> str:
        self._require_network()
        token = self.oauth.token()
        limit = _clamp(max_results)
        query = urlencode(
            {
                "pageSize": str(limit),
                "fields": "files(id,name,mimeType,modifiedTime)",
            }
        )
        payload = request_json(
            f"https://www.googleapis.com/drive/v3/files?{query}",
            token=token,
            opener=self._opener,
        )
        files = payload.get("files") if isinstance(payload.get("files"), list) else []
        lines = [f"drive files: {len(files)}"]
        for row in files[:limit]:
            if not isinstance(row, dict):
                continue
            name = row.get("name") if isinstance(row.get("name"), str) else "(unnamed)"
            lines.append(f"- {name}")
        return guard_untrusted("\n".join(lines), source="gws:drive")

    def refuse_write(self, action: str) -> str:
        raise GwsSecurityError(
            _bilingual(
                f"{action} is not enabled in this cut; sending and deleting stay human",
                f"{action} در این برش فعال نیست؛ ارسال و حذف دست انسان می‌ماند",
            )
        )

    def _require_network(self) -> None:
        if not _network_enabled():
            raise GwsSecurityError(
                _bilingual(
                    "owner has not enabled DREAM_ALLOW_NETWORK",
                    "مالک DREAM_ALLOW_NETWORK را فعال نکرده است",
                )
            )


def _clamp(value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 5
    return min(max(number, 1), 10)


def get_service() -> GoogleWorkspaceService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = GoogleWorkspaceService()
    return _SERVICE


def reset_service() -> None:
    global _SERVICE
    _SERVICE = None
