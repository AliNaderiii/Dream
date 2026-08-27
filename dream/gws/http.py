"""Allowlisted HTTPS to Google APIs. No arbitrary URLs."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from dream.gws.errors import GwsSecurityError

TIMEOUT_SECONDS = 10
RESPONSE_CAP = 200_000
ALLOWED_HOSTS = frozenset(
    {
        "oauth2.googleapis.com",
        "gmail.googleapis.com",
        "www.googleapis.com",
    }
)


def _require_host(address: str) -> str:
    parsed = urlsplit(address)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or host not in ALLOWED_HOSTS:
        raise GwsSecurityError("Google API host is not on the allow-list")
    if parsed.username or parsed.password:
        raise GwsSecurityError("credentials in URL are not allowed")
    return address


def request_json(
    address: str,
    *,
    method: str = "GET",
    token: str | None = None,
    data: bytes | None = None,
    opener: Any = urlopen,
) -> dict[str, Any]:
    """GET/POST JSON on an allowlisted Google host."""
    _require_host(address)
    headers = {"Accept": "application/json", "User-Agent": "dream-assistant/0.4.6"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(address, data=data, headers=headers, method=method)
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            _require_host(response.geturl())
            body = response.read(RESPONSE_CAP + 1)
    except HTTPError as exc:
        raise GwsSecurityError(f"Google API HTTP {exc.code}") from None
    except (URLError, OSError, TimeoutError) as exc:
        raise GwsSecurityError("Google API could not be reached") from exc
    if len(body) > RESPONSE_CAP:
        raise GwsSecurityError("Google API response exceeded the cap")
    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise GwsSecurityError("Google API returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise GwsSecurityError("Google API returned a non-object")
    return payload


def form_body(fields: dict[str, str]) -> bytes:
    return urlencode(fields).encode("utf-8")
