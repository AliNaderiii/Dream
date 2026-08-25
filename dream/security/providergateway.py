"""Credential and egress policy for the provider hubs (P6, L9-E).

P5 gave Dream an optional tool gateway and a matrix of local serving
runtimes. That is a credential surface and a network surface at once, so
this module is the policy in front of both. It **calls** into
:mod:`dream.providerhubs` (``ToolGateway``, ``RUNTIME_SPECS``) and never
edits it.

Credentials:

* **least privilege, per tool.** A token is minted for exactly one
  gateway tool (``web_search``, ``image``, ``tts``, ``browser``) and one
  scope (``read`` or ``use``). There is no "all tools" token and no
  global scope — :func:`mint_token` refuses both.
* **rotatable and revocable.** :meth:`ScopedTokenStore.rotate` replaces
  the secret while keeping the grant, so a suspected leak costs one call.
  Verification is constant time (``secrets.compare_digest``).
* **never in logs, traces or RPC.** Only a SHA-256 digest is stored; the
  plaintext exists once, at mint time, for the caller to hand to the
  tool. :func:`safe_snapshot` and :func:`redact_headers` are the only
  shapes that leave this module, and the audit asserts a seeded token
  never appears in them.

Egress:

* **probes are bounded and non-exfiltrating.** :func:`probe_runtime`
  refuses any endpoint that is not the configured one for that runtime,
  refuses non-HTTP schemes, refuses redirects, caps the read, caps the
  timeout, and sends **no** credential header — a health check must never
  be a channel for one.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from dream.providerhubs.types import GATEWAY_TOOLS, RUNTIME_SPECS
from dream.security.secrets import redact_structure, redact_text

__all__ = [
    "GATEWAY_SCOPES",
    "MAX_PROBE_BYTES",
    "MAX_PROBE_TIMEOUT",
    "TOKEN_PREFIX",
    "GatewayPolicyError",
    "GatewayRefusal",
    "ProbeResult",
    "ScopedToken",
    "ScopedTokenStore",
    "mint_token",
    "probe_runtime",
    "redact_headers",
    "safe_snapshot",
    "tool_enabled",
]

#: The only scopes a gateway token may carry. There is no ``admin`` and no
#: wildcard: a token that can do everything is a token worth stealing.
GATEWAY_SCOPES: tuple[str, ...] = ("read", "use")

TOKEN_PREFIX = "dgw_"
MAX_PROBE_BYTES = 64 * 1024
MAX_PROBE_TIMEOUT = 5.0
_DEFAULT_TTL = 24 * 3600.0


@dataclass(frozen=True)
class GatewayRefusal:
    """A bilingual, fail-closed refusal from the gateway policy."""

    code: str
    reason_en: str
    reason_fa: str
    detail: str = ""

    def message(self) -> str:
        tail = f" ({self.detail})" if self.detail else ""
        return f"{self.reason_en}{tail}\n{self.reason_fa}{tail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason_en": self.reason_en,
            "reason_fa": self.reason_fa,
            "detail": self.detail,
        }


def _refuse(code: str, en: str, fa: str, detail: str = "") -> GatewayRefusal:
    return GatewayRefusal(code=code, reason_en=en, reason_fa=fa, detail=detail)


class GatewayPolicyError(PermissionError):
    """Raised when a credential request violates least privilege."""

    def __init__(self, refusal: GatewayRefusal) -> None:
        super().__init__(refusal.message())
        self.refusal = refusal


# --------------------------------------------------------------------------- #
# Scoped tokens
# --------------------------------------------------------------------------- #


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScopedToken:
    """A grant record. The plaintext secret is deliberately absent."""

    token_id: str
    tool: str
    scope: str
    digest: str
    created_at: float
    expires_at: float
    rotated_from: str | None = None
    label: str = ""

    def expired(self, *, now: float | None = None) -> bool:
        stamp = time.time() if now is None else float(now)
        return stamp >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """A wire-safe view. Contains no secret and no digest."""
        return {
            "token_id": self.token_id,
            "tool": self.tool,
            "scope": self.scope,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "rotated": self.rotated_from is not None,
            "label": self.label,
        }


def mint_token(
    tool: str,
    scope: str = "read",
    *,
    ttl_seconds: float = _DEFAULT_TTL,
    label: str = "",
) -> tuple[str, ScopedToken]:
    """Mint one least-privilege token. Returns ``(secret, record)``.

    The secret is returned exactly once. Everything persisted afterwards
    is a digest, so a dump of Dream's state cannot be replayed as a token.
    """
    if tool not in GATEWAY_TOOLS:
        raise GatewayPolicyError(
            _refuse(
                "unknown_tool",
                f"token refused: {tool!r} is not a gateway tool",
                f"توکن رد شد: {tool!r} ابزار درگاه نیست",
            )
        )
    if scope not in GATEWAY_SCOPES:
        raise GatewayPolicyError(
            _refuse(
                "bad_scope",
                f"token refused: scope must be one of {GATEWAY_SCOPES}",
                f"توکن رد شد: دامنه باید یکی از {GATEWAY_SCOPES} باشد",
            )
        )
    if not 60.0 <= float(ttl_seconds) <= 30 * 24 * 3600.0:
        raise GatewayPolicyError(
            _refuse(
                "bad_ttl",
                "token refused: a gateway token lives between one minute and 30 days",
                "توکن رد شد: عمر توکن درگاه بین یک دقیقه تا سی روز است",
            )
        )
    secret = TOKEN_PREFIX + secrets.token_hex(24)
    now = time.time()
    record = ScopedToken(
        token_id=f"tok_{secrets.token_hex(8)}",
        tool=tool,
        scope=scope,
        digest=_digest(secret),
        created_at=now,
        expires_at=now + float(ttl_seconds),
        label=str(label)[:60],
    )
    return secret, record


class ScopedTokenStore:
    """In-memory registry of per-tool gateway grants.

    Deliberately not persisted here: the OS keychain
    (``KeychainCredentialStore``) owns durable secrets. This store owns the
    *grant* — which tool, which scope, until when — and verifies presented
    secrets in constant time.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, ScopedToken] = {}
        self._lock = threading.RLock()

    def issue(
        self,
        tool: str,
        scope: str = "read",
        *,
        ttl_seconds: float = _DEFAULT_TTL,
        label: str = "",
    ) -> tuple[str, ScopedToken]:
        secret, record = mint_token(tool, scope, ttl_seconds=ttl_seconds, label=label)
        with self._lock:
            self._tokens[record.token_id] = record
        return secret, record

    def rotate(
        self, token_id: str, *, ttl_seconds: float = _DEFAULT_TTL
    ) -> tuple[str, ScopedToken]:
        """Replace a token's secret, keeping its tool and scope."""
        with self._lock:
            existing = self._tokens.get(str(token_id))
            if existing is None:
                raise GatewayPolicyError(
                    _refuse(
                        "unknown_token",
                        "rotation refused: no such gateway token",
                        "چرخش رد شد: چنین توکن درگاهی وجود ندارد",
                    )
                )
            secret, fresh = mint_token(
                existing.tool, existing.scope, ttl_seconds=ttl_seconds, label=existing.label
            )
            replacement = ScopedToken(
                token_id=fresh.token_id,
                tool=fresh.tool,
                scope=fresh.scope,
                digest=fresh.digest,
                created_at=fresh.created_at,
                expires_at=fresh.expires_at,
                rotated_from=existing.token_id,
                label=existing.label,
            )
            self._tokens.pop(existing.token_id, None)
            self._tokens[replacement.token_id] = replacement
        return secret, replacement

    def revoke(self, token_id: str) -> bool:
        with self._lock:
            return self._tokens.pop(str(token_id), None) is not None

    def get(self, token_id: str) -> ScopedToken | None:
        with self._lock:
            return self._tokens.get(str(token_id))

    def verify(
        self, secret: str, *, tool: str, scope: str = "read", now: float | None = None
    ) -> tuple[bool, GatewayRefusal | None]:
        """Constant-time check that *secret* grants *scope* on *tool*."""
        if not isinstance(secret, str) or not secret:
            return False, _refuse(
                "no_token",
                "gateway refused: no token was presented",
                "درگاه رد کرد: توکنی ارائه نشد",
            )
        presented = _digest(secret)
        matched: ScopedToken | None = None
        with self._lock:
            candidates = list(self._tokens.values())
        for record in candidates:
            # compare_digest on every candidate: no early exit, no timing hint.
            if hmac.compare_digest(presented, record.digest):
                matched = record
        if matched is None:
            return False, _refuse(
                "unknown_token",
                "gateway refused: the token is not recognised",
                "درگاه رد کرد: توکن شناخته نشد",
            )
        if matched.expired(now=now):
            return False, _refuse(
                "expired_token",
                "gateway refused: the token has expired; rotate it",
                "درگاه رد کرد: توکن منقضی شده است؛ آن را بچرخانید",
            )
        if matched.tool != tool:
            return False, _refuse(
                "wrong_tool",
                f"gateway refused: this token is scoped to {matched.tool!r}, not {tool!r}",
                f"درگاه رد کرد: این توکن برای {matched.tool!r} است، نه {tool!r}",
            )
        if scope == "use" and matched.scope != "use":
            return False, _refuse(
                "insufficient_scope",
                "gateway refused: this token is read-only",
                "درگاه رد کرد: این توکن فقط خواندنی است",
            )
        return True, None

    def snapshot(self) -> list[dict[str, Any]]:
        """Wire-safe listing: grants without secrets or digests."""
        with self._lock:
            return [record.to_dict() for record in self._tokens.values()]


# --------------------------------------------------------------------------- #
# Per-tool enablement, read through the P5 gateway
# --------------------------------------------------------------------------- #


def tool_enabled(gateway: Any, tool: str) -> tuple[bool, GatewayRefusal | None]:
    """Whether *tool* is enabled on the P5 ``ToolGateway``.

    Fail-closed: an unknown tool, a gateway that is switched off, or a
    snapshot Dream cannot read all deny.
    """
    if tool not in GATEWAY_TOOLS:
        return False, _refuse(
            "unknown_tool",
            f"gateway refused: {tool!r} is not a gateway tool",
            f"درگاه رد کرد: {tool!r} ابزار درگاه نیست",
        )
    try:
        snapshot = gateway.snapshot()
    except Exception:
        return False, _refuse(
            "gateway_unreadable",
            "gateway refused: the gateway state could not be read",
            "درگاه رد کرد: وضعیت درگاه خوانده نشد",
        )
    if not isinstance(snapshot, dict) or not snapshot.get("enabled"):
        return False, _refuse(
            "gateway_disabled",
            "gateway refused: the optional tool gateway is off",
            "درگاه رد کرد: درگاه ابزار اختیاری خاموش است",
        )
    for row in snapshot.get("tools") or []:
        if isinstance(row, dict) and row.get("id") == tool:
            if row.get("enabled"):
                return True, None
            return False, _refuse(
                "tool_disabled",
                f"gateway refused: {tool!r} is disabled",
                f"درگاه رد کرد: {tool!r} غیرفعال است",
            )
    return False, _refuse(
        "tool_missing",
        f"gateway refused: {tool!r} is not present in the gateway",
        f"درگاه رد کرد: {tool!r} در درگاه موجود نیست",
    )


# --------------------------------------------------------------------------- #
# Log/trace/RPC hygiene
# --------------------------------------------------------------------------- #

_CREDENTIAL_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "cookie",
        "set-cookie",
        "x-dream-token",
    }
)


def redact_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    """Header map with every credential-bearing value replaced."""
    out: dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key)
        if name.lower() in _CREDENTIAL_HEADERS:
            out[name] = "[REDACTED:header]"
        else:
            out[name] = redact_text(str(value))
    return out


def safe_snapshot(payload: Any) -> Any:
    """The only shape gateway state may take on a wire or in a log.

    Runs the L6 value scanner and then drops any key whose *name* says it
    holds a secret, so a future field cannot leak by being added.
    """
    scrubbed = redact_structure(payload)
    return _drop_secret_keys(scrubbed)


_SECRET_KEY_HINTS = ("token", "secret", "api_key", "apikey", "password", "credential", "digest")


def _drop_secret_keys(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key).lower()
            if name in {"token_id", "credential_configured"}:
                out[key] = item
                continue
            if any(hint in name for hint in _SECRET_KEY_HINTS):
                out[key] = "[REDACTED:field]"
                continue
            out[key] = _drop_secret_keys(item)
        return out
    if isinstance(value, list):
        return [_drop_secret_keys(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_drop_secret_keys(item) for item in value)
    return value


# --------------------------------------------------------------------------- #
# Bounded, non-exfiltrating probes
# --------------------------------------------------------------------------- #


@dataclass
class ProbeResult:
    """One bounded health probe. Carries no credential, ever."""

    ok: bool
    status: int = 0
    latency_ms: float = 0.0
    body_preview: str = ""
    truncated: bool = False
    refusal: GatewayRefusal | None = None
    headers_sent: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return safe_snapshot(
            {
                "ok": self.ok,
                "status": self.status,
                "latency_ms": self.latency_ms,
                "body_preview": self.body_preview,
                "truncated": self.truncated,
                "refusal": self.refusal.to_dict() if self.refusal else None,
                "headers_sent": self.headers_sent,
            }
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an unreviewed destination; the probe refuses to follow."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, D102
        return None


def _configured_endpoints(runtime_id: str) -> set[str]:
    spec = RUNTIME_SPECS.get(runtime_id) or {}
    endpoints = {str(spec.get("endpoint", "")).rstrip("/")}
    return {endpoint for endpoint in endpoints if endpoint}


def _endpoint_allowed(runtime_id: str, endpoint: str, extra_allowed: set[str]) -> bool:
    candidate = str(endpoint or "").rstrip("/")
    return candidate in (_configured_endpoints(runtime_id) | {e.rstrip("/") for e in extra_allowed})


def _host_is_local(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def probe_runtime(
    runtime_id: str,
    *,
    endpoint: str | None = None,
    path: str = "/models",
    opener: Any = None,
    timeout: float = 1.5,
    allowed_endpoints: set[str] | None = None,
    require_local: bool = True,
) -> ProbeResult:
    """A bounded GET against a *configured* runtime endpoint.

    Refuses: unknown runtimes, endpoints that were never configured,
    non-HTTP schemes, non-local hosts (unless the owner widened the
    allowlist), and redirects. Sends no credential header, reads at most
    :data:`MAX_PROBE_BYTES`, and always carries a timeout.
    """
    if runtime_id not in RUNTIME_SPECS:
        return ProbeResult(
            ok=False,
            refusal=_refuse(
                "unknown_runtime",
                f"probe refused: {runtime_id!r} is not a known runtime",
                f"کاوش رد شد: {runtime_id!r} زمان‌اجرای شناخته‌شده‌ای نیست",
            ),
        )
    target_base = (endpoint or str(RUNTIME_SPECS[runtime_id]["endpoint"])).rstrip("/")
    extra = {str(item) for item in (allowed_endpoints or set())}
    if not _endpoint_allowed(runtime_id, target_base, extra):
        return ProbeResult(
            ok=False,
            refusal=_refuse(
                "endpoint_not_configured",
                "probe refused: that endpoint is not the configured one for this runtime",
                "کاوش رد شد: این نشانی، نشانی پیکربندی‌شدهٔ این زمان‌اجرا نیست",
            ),
        )
    safe_path = "/" + str(path or "").lstrip("/")
    if ".." in safe_path or "\\" in safe_path or "@" in safe_path:
        return ProbeResult(
            ok=False,
            refusal=_refuse(
                "bad_path",
                "probe refused: the probe path is not a simple endpoint path",
                "کاوش رد شد: مسیر کاوش یک مسیر ساده نیست",
            ),
        )
    url = f"{target_base}{safe_path}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ProbeResult(
            ok=False,
            refusal=_refuse(
                "bad_scheme",
                "probe refused: only http and https endpoints may be probed",
                "کاوش رد شد: فقط نشانی‌های http و https کاوش می‌شوند",
            ),
        )
    if parsed.username or parsed.password:
        return ProbeResult(
            ok=False,
            refusal=_refuse(
                "credential_in_url",
                "probe refused: credentials must never travel in a URL",
                "کاوش رد شد: اعتبارنامه هرگز نباید در نشانی جابه‌جا شود",
            ),
        )
    if require_local and not _host_is_local(parsed.hostname or ""):
        return ProbeResult(
            ok=False,
            refusal=_refuse(
                "non_local_host",
                "probe refused: local runtime probes may only reach the loopback interface",
                "کاوش رد شد: کاوش زمان‌اجرای محلی فقط به رابط داخلی مجاز است",
            ),
        )

    bounded_timeout = max(0.1, min(float(timeout), MAX_PROBE_TIMEOUT))
    # No credential header. A health check that can carry a token is a
    # health check that can leak one.
    headers = {"Accept": "application/json", "User-Agent": "Dream/probe"}
    request = urllib.request.Request(url, headers=headers, method="GET")
    started = time.monotonic()
    send = opener or urllib.request.build_opener(_NoRedirect()).open
    try:
        with send(request, timeout=bounded_timeout) as response:
            raw = response.read(MAX_PROBE_BYTES + 1)
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return ProbeResult(
            ok=False,
            status=int(getattr(exc, "code", 0) or 0),
            latency_ms=round((time.monotonic() - started) * 1000, 2),
            headers_sent=redact_headers(headers),
            refusal=_refuse(
                "http_error",
                "probe failed: the runtime answered with an error status",
                "کاوش ناموفق: زمان‌اجرا با وضعیت خطا پاسخ داد",
            ),
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ProbeResult(
            ok=False,
            latency_ms=round((time.monotonic() - started) * 1000, 2),
            headers_sent=redact_headers(headers),
            refusal=_refuse(
                "unreachable",
                "probe failed: the runtime is not reachable",
                "کاوش ناموفق: زمان‌اجرا در دسترس نیست",
            ),
        )
    truncated = len(raw) > MAX_PROBE_BYTES
    body = raw[:MAX_PROBE_BYTES].decode("utf-8", "replace")
    return ProbeResult(
        ok=True,
        status=status,
        latency_ms=round((time.monotonic() - started) * 1000, 2),
        body_preview=redact_text(body[:500]),
        truncated=truncated,
        headers_sent=redact_headers(headers),
    )
