"""PKCE OAuth for Google Workspace. Loopback redirect only. Tokens in keychain."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from dream.gws.errors import GwsSecurityError
from dream.gws.http import form_body, request_json
from dream.model_providers import KeychainCredentialStore

ACCOUNT = "gws"
SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT = "http://127.0.0.1:17463/callback"
STATE_TTL = 600


def _bilingual(en: str, fa: str) -> str:
    return f"{en} / {fa}"


def _client_id() -> str:
    value = os.environ.get("DREAM_GOOGLE_CLIENT_ID", "").strip()
    if not value or "EXAMPLE" in value.upper():
        raise GwsSecurityError(
            _bilingual(
                "set DREAM_GOOGLE_CLIENT_ID to your Google Cloud desktop OAuth client",
                "DREAM_GOOGLE_CLIENT_ID را روی کلاینت دسکتاپ Google Cloud بگذارید",
            )
        )
    return value


def _client_secret() -> str:
    return os.environ.get("DREAM_GOOGLE_CLIENT_SECRET", "").strip()


class GoogleOAuth:
    """One in-memory PKCE attempt plus keychain tokens."""

    def __init__(
        self,
        credentials: KeychainCredentialStore | None = None,
        opener: Any = None,
    ) -> None:
        self.credentials = credentials or KeychainCredentialStore()
        self._opener = opener
        self._pending: dict[str, dict[str, Any]] = {}

    def connected(self) -> bool:
        return self.credentials.has(ACCOUNT, "oauth_access_token")

    def begin(self) -> dict[str, str]:
        client_id = _client_id()
        state = generate_token(48)
        verifier = generate_token(96)
        challenge = create_s256_code_challenge(verifier)
        self._pending[state] = {
            "verifier": verifier,
            "created_at": time.monotonic(),
        }
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": REDIRECT,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return {
            "authorization_url": f"{AUTHORIZE_URL}?{query}",
            "state": state,
            "redirect_uri": REDIRECT,
        }

    def complete(self, state: str, code_or_url: str) -> dict[str, Any]:
        pending = self._pending.pop(state, None)
        if pending is None:
            raise GwsSecurityError("invalid OAuth state")
        if (time.monotonic() - float(pending["created_at"])) > STATE_TTL:
            raise GwsSecurityError("OAuth state expired")
        code = _extract_code(code_or_url)
        fields = {
            "client_id": _client_id(),
            "code": code,
            "code_verifier": str(pending["verifier"]),
            "redirect_uri": REDIRECT,
            "grant_type": "authorization_code",
        }
        secret = _client_secret()
        if secret:
            if "EXAMPLE" in secret.upper():
                raise GwsSecurityError("example client secrets are refused")
            fields["client_secret"] = secret
        kwargs: dict[str, Any] = {}
        if self._opener is not None:
            kwargs["opener"] = self._opener
        tokens = request_json(TOKEN_URL, method="POST", data=form_body(fields), **kwargs)
        access = tokens.get("access_token")
        if not isinstance(access, str) or not access or access.startswith("sk_EXAMPLE"):
            raise GwsSecurityError("OAuth response did not include a real access token")
        self.credentials.set(ACCOUNT, access, "oauth_access_token")
        refresh = tokens.get("refresh_token")
        if isinstance(refresh, str) and refresh:
            self.credentials.set(ACCOUNT, refresh, "oauth_refresh_token")
        return {"connected": True, "scopes": list(SCOPES)}

    def token(self) -> str:
        access = self.credentials.get(ACCOUNT, "oauth_access_token") or ""
        if not access:
            raise GwsSecurityError(
                _bilingual(
                    "Google is not connected; complete OAuth on the Google page",
                    "گوگل وصل نیست؛ OAuth را از صفحهٔ Google تمام کنید",
                )
            )
        return access

    def disconnect(self) -> dict[str, bool]:
        self.credentials.purge(ACCOUNT)
        return {"connected": False}


def _extract_code(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise GwsSecurityError("authorization code is required")
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlsplit(text)
        host = (parsed.hostname or "").lower()
        if host not in {"127.0.0.1", "localhost"}:
            raise GwsSecurityError("OAuth redirect must be loopback")
        code = (parse_qs(parsed.query).get("code") or [""])[0]
        if not code:
            raise GwsSecurityError("redirect URL did not include a code")
        return code
    return text
