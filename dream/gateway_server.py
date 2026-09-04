"""Web Gateway — FastAPI HTTP server for remote access to Dream.

Serves the same React desktop UI as a web application, with token
authentication, read-only mode, LAN discovery via mDNS, and TLS support.

The gateway runs as part of the Python sidecar or as a standalone process.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import platform
import secrets
import shutil
import socket
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("dream.gateway")


# ---------------------------------------------------------------------------
# Token authentication
# ---------------------------------------------------------------------------


class TokenScope(str, Enum):
    """Access scopes for gateway tokens."""

    READ = "read"  # View-only access
    WRITE = "write"  # Full interaction (chat, session management, etc.)


class GatewayTokenStoreError(RuntimeError):
    """A token store could not be loaded, migrated, or persisted safely."""


#: Minimum characters accepted when revoking by a non-secret token id.
MIN_TOKEN_ID_LENGTH = 12
_VERIFIER_PREFIX = "tok_"


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def _hash_secret(raw: str) -> str:
    """Return a hex SHA-256 verifier for a high-entropy raw token.

    The raw value carries ~160 bits of `os.urandom`-derived entropy (two
    UUID4s), so a plain digest is not brute-forceable if the store is read
    without also possessing the secret. A separate pepper would need to be
    stored in a second credential location and is deliberately out of scope
    for a single-owner local-first gateway.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _token_id(raw: str) -> str:
    return _VERIFIER_PREFIX + _hash_secret(raw)[:24]


class TokenManager:
    """Manages authentication tokens for the web gateway.

    Raw tokens are returned only once by :meth:`create_token` and
    :meth:`rotate_token`. Persisted state stores an identifier, a masked
    prefix, and a SHA-256 *verifier* (never the raw secret). The store is
    written atomically with owner-only permissions and is protected by a
    write lock.

    ``load_error`` is non-empty when the on-disk store is malformed or the
    legacy plaintext store could not be migrated; callers must fail closed.
    """

    def __init__(self, tokens_path: str | None = None) -> None:
        self._tokens_path = tokens_path or os.path.expanduser(
            "~/.dream/gateway_tokens.json"
        )
        self._tokens: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.load_error: str | None = None
        self._load()

    @property
    def has_tokens(self) -> bool:
        return len(self._tokens) > 0

    def get_setup_token(self) -> str | None:
        """Return the first admin/write token's *id*, or ``None``.

        The id is a non-secret handle used by status screens; it is never a
        usable credential.
        """
        for tid, info in self._tokens.items():
            if info.get("scope") == "write":
                return tid
        return None

    def create_token(
        self,
        scope: TokenScope = TokenScope.WRITE,
        label: str = "Default",
    ) -> str:
        """Create a new authentication token and return its raw value once.

        Args:
            scope: ``"read"`` or ``"write"``.
            label: Human-readable label for this token.

        Returns:
            The raw token string. It is not retrievable later.
        """
        raw = f"drm_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"
        token_id = _token_id(raw)
        with self._lock:
            row = self._record(raw, scope=scope, label=label)
            self._tokens[token_id] = row
            try:
                self._save()
            except OSError as exc:
                self._tokens.pop(token_id, None)
                raise GatewayTokenStoreError(
                    _bilingual(
                        "failed to persist gateway token",
                        "\u0630\u062e\u06cc\u0631\u0647\u0654 \u062a\u0648\u06a9\u0646 "
                        "\u062f\u0631\u06af\u0627\u0647 \u0634\u06a9\u0633\u062a "
                        "\u062e\u0648\u0631\u062f",
                    )
                ) from exc
        return raw

    def rotate_token(self, token: str) -> str | None:
        """Rotate a token by its raw value or non-secret id.

        Returns the new raw value once, or ``None`` when no token matches.
        """
        key = self._lookup_key(token)
        if key is None:
            return None
        with self._lock:
            info = self._tokens.get(key)
            if info is None:
                return None
            raw = f"drm_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"
            replacement = self._record(
                raw,
                scope=TokenScope(info.get("scope", TokenScope.READ.value)),
                label=str(info.get("label") or "Rotated"),
            )
            self._tokens.pop(key, None)
            self._tokens[replacement["id"]] = replacement
            try:
                self._save()
            except OSError as exc:
                self._tokens.pop(replacement["id"], None)
                self._tokens[key] = info
                raise GatewayTokenStoreError(
                    _bilingual(
                        "failed to persist rotated gateway token",
                        "\u0630\u062e\u06cc\u0631\u0647\u0654 \u062a\u0648\u06a9\u0646 "
                        "\u0686\u0631\u062e\u06cc\u062f\u0647\u0654 "
                        "\u062f\u0631\u06af\u0627\u0647 \u0634\u06a9\u0633\u062a "
                        "\u062e\u0648\u0631\u062f",
                    )
                ) from exc
            return raw

    def revoke_token(self, token: str) -> bool:
        """Revoke a token by its raw value or non-secret id.

        Returns ``True`` when a token was revoked. Prefix matching is not
        used; callers must supply the full raw value or the id returned by
        :meth:`list_tokens`.
        """
        key = self._lookup_key(token)
        if key is None:
            return False
        with self._lock:
            if key not in self._tokens:
                return False
            self._tokens.pop(key, None)
            try:
                self._save()
            except OSError as exc:
                raise GatewayTokenStoreError(
                    _bilingual(
                        "failed to persist token revocation",
                        "\u0630\u062e\u06cc\u0631\u0647\u0654 \u0627\u0628\u0637\u0627\u0644 "
                        "\u062a\u0648\u06a9\u0646 \u0634\u06a9\u0633\u062a "
                        "\u062e\u0648\u0631\u062f",
                    )
                ) from exc
            return True

    def verify_token(
        self, token: str, required_scope: TokenScope = TokenScope.READ
    ) -> dict[str, Any] | None:
        """Verify a token and return its info, or ``None`` if invalid.

        The candidate's verifier is compared against every stored verifier
        with :func:`secrets.compare_digest`, so verification cost and timing
        never depend on how much of a guess is right.
        """
        if not isinstance(token, str) or not token:
            return None
        candidate = _hash_secret(token)
        tid: str | None = None
        info: dict[str, Any] | None = None
        with self._lock:
            for current_tid, row in self._tokens.items():
                if secrets.compare_digest(candidate, str(row.get("verifier", ""))):
                    tid, info = current_tid, row
                    break
            if info is None:
                return None
            token_scope = TokenScope(info["scope"])
            safe = {
                "id": tid,
                "scope": info["scope"],
                "label": info["label"],
                "created_at": info["created_at"],
                "last_used_at": info.get("last_used_at"),
            }
            if required_scope == TokenScope.READ and token_scope in (
                TokenScope.READ,
                TokenScope.WRITE,
            ):
                info["last_used_at"] = time.time()
                safe["last_used_at"] = info["last_used_at"]
                return safe
            if required_scope == TokenScope.WRITE and token_scope == TokenScope.WRITE:
                info["last_used_at"] = time.time()
                safe["last_used_at"] = info["last_used_at"]
                return safe
            return None

    def list_tokens(self) -> list[dict[str, Any]]:
        """List token metadata without raw values or verifiers."""
        with self._lock:
            return [
                {
                    "id": tid,
                    "prefix": info.get("prefix") or _mask_raw_for_test(tid),
                    "scope": info["scope"],
                    "label": info["label"],
                    "created_at": info["created_at"],
                    "last_used_at": info.get("last_used_at"),
                }
                for tid, info in self._tokens.items()
            ]

    def all_tokens(self) -> dict[str, dict[str, Any]]:
        """Return token metadata keyed by non-secret id.

        This intentionally excludes raw secrets and verifiers; it is safe for
        status screens and bridge serialisation.
        """
        return {row["id"]: row for row in self.list_tokens()}

    # -- internals ------------------------------------------------------- #

    def _record(
        self, raw: str, *, scope: TokenScope, label: str
    ) -> dict[str, Any]:
        return {
            "id": _token_id(raw),
            "prefix": raw[:12] + "...",
            "scope": scope.value,
            "label": str(label or "Default")[:200],
            "created_at": time.time(),
            "last_used_at": None,
            "verifier": _hash_secret(raw),
        }

    def _lookup_key(self, candidate: str) -> str | None:
        """Resolve a raw secret or a token id to a store key."""
        if not isinstance(candidate, str) or not candidate:
            return None
        if candidate.startswith(_VERIFIER_PREFIX) and len(candidate) >= MIN_TOKEN_ID_LENGTH:
            return candidate if candidate in self._tokens else None
        verifier = _hash_secret(candidate)
        with self._lock:
            for tid, row in self._tokens.items():
                if secrets.compare_digest(verifier, str(row.get("verifier", ""))):
                    return tid
        return None

    def _load(self) -> None:
        self.load_error = None
        path = Path(self._tokens_path)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self._tokens = {}
            return
        except (OSError, ValueError) as exc:
            self._tokens = {}
            self.load_error = _bilingual(
                "gateway token store is unreadable; the web gateway is disabled",
                "\u0641\u0627\u06cc\u0644 \u062a\u0648\u06a9\u0646 "
                "\u062f\u0631\u06af\u0627\u0647 \u0642\u0627\u0628\u0644 "
                "\u062e\u0648\u0627\u0646\u062f\u0646 \u0646\u06cc\u0633\u062a\u061b "
                "\u062f\u0631\u06af\u0627\u0647 \u0648\u0628 "
                "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a",
            )
            logger.warning("Gateway token store unreadable: %s", exc)
            return

        if not isinstance(data, dict):
            self._tokens = {}
            self.load_error = _bilingual(
                "gateway token store is malformed; the web gateway is disabled",
                "\u0641\u0627\u06cc\u0644 \u062a\u0648\u06a9\u0646 "
                "\u062f\u0631\u06af\u0627\u0647 \u0646\u0627\u0642\u0635 "
                "\u0627\u0633\u062a\u061b \u062f\u0631\u06af\u0627\u0647 \u0648\u0628 "
                "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a",
            )
            return

        if data.get("version") == 2 and isinstance(data.get("tokens"), dict):
            self._tokens = {
                str(tid): row
                for tid, row in data["tokens"].items()
                if isinstance(row, dict)
                and str(row.get("scope")) in {TokenScope.READ.value, TokenScope.WRITE.value}
                and isinstance(row.get("verifier"), str)
            }
            return

        if any(str(key).startswith("drm_") for key in data):
            self._migrate_v1(data)
            return

        self._tokens = {}
        self.load_error = _bilingual(
            "gateway token store has an unsupported format; the web gateway is disabled",
            "\u0641\u0631\u0645\u062a \u0641\u0627\u06cc\u0644 "
            "\u062a\u0648\u06a9\u0646 \u062f\u0631\u06af\u0627\u0647 "
            "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc "
            "\u0646\u0645\u06cc‌\u0634\u0648\u062f\u061b "
            "\u062f\u0631\u06af\u0627\u0647 \u0648\u0628 "
            "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a",
        )

    def _migrate_v1(self, data: dict[str, Any]) -> None:
        """Migrate a legacy plaintext store atomically and fail closed."""
        migrated: dict[str, dict[str, Any]] = {}
        for raw, row in data.items():
            if not isinstance(raw, str) or not raw.startswith("drm_"):
                raise GatewayTokenStoreError(
                    _bilingual(
                        "legacy gateway token store contains an invalid row",
                        "\u0641\u0627\u06cc\u0644 \u0642\u062f\u06cc\u0645\u06cc "
                        "\u062a\u0648\u06a9\u0646 \u062f\u0631\u06af\u0627\u0647 "
                        "\u062d\u0627\u0648\u06cc \u0631\u062f\u06cc\u0641 "
                        "\u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a",
                    )
                )
            info = row if isinstance(row, dict) else {}
            scope = info.get("scope", TokenScope.WRITE.value)
            if scope not in {TokenScope.READ.value, TokenScope.WRITE.value}:
                scope = TokenScope.WRITE.value
            record = self._record(
                raw,
                scope=TokenScope(scope),
                label=str(info.get("label") or "Migrated"),
            )
            record["created_at"] = float(info.get("created_at") or time.time())
            migrated[record["id"]] = record

        old_path = str(self._tokens_path) + ".bak"
        try:
            shutil.copy2(self._tokens_path, old_path)
        except OSError as exc:
            self._tokens = {}
            self.load_error = _bilingual(
                "could not back up legacy gateway tokens; the web gateway is disabled",
                "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646‌\u06af\u06cc\u0631\u06cc "
                "\u0627\u0632 \u062a\u0648\u06a9\u0646‌\u0647\u0627\u06cc "
                "\u0642\u062f\u06cc\u0645\u06cc \u062f\u0631\u06af\u0627\u0647 "
                "\u0646\u0627\u0645\u0648\u0641\u0642 \u0628\u0648\u062f\u061b "
                "\u062f\u0631\u06af\u0627\u0647 \u0648\u0628 "
                "\u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a",
            )
            logger.warning("Gateway token migration backup failed: %s", exc)
            return

        self._tokens = migrated
        try:
            self._save()
        except OSError as exc:
            self._tokens = {}
            self.load_error = _bilingual(
                "could not persist migrated gateway tokens; the web gateway is disabled",
                "\u0630\u062e\u06cc\u0631\u0647\u0654 "
                "\u062a\u0648\u06a9\u0646\u200c\u0647\u0627\u06cc "
                "\u0645\u0647\u0627\u062c\u0631\u062a\u200c\u06cc\u0627\u0641\u062a\u0647\u0654 "
                "\u062f\u0631\u06af\u0627\u0647 \u0646\u0627\u0645\u0648\u0641\u0642 "
                "\u0628\u0648\u062f\u061b \u062f\u0631\u06af\u0627\u0647 "
                "\u0648\u0628 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a",
            )
            logger.warning("Gateway token migration save failed: %s", exc)
            return

        try:
            os.chmod(str(self._tokens_path), 0o600)
        except OSError:
            pass
        try:
            os.remove(old_path)
        except OSError:
            pass
        logger.info("Migrated %d legacy gateway token(s) to verifier storage", len(migrated))

    def _save(self) -> None:
        path = Path(self._tokens_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": 2,
                    "tokens": self._tokens,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, str(path))
        try:
            os.chmod(str(path), 0o600)
        except OSError:
            pass


def _mask_raw_for_test(_token_id: str) -> str:
    """Fallback masked prefix for rows predating the ``prefix`` field."""
    return "drm_***"


# ---------------------------------------------------------------------------
# Security headers + per-token rate limiting (SEC Stage D, G-23/G-24)
# ---------------------------------------------------------------------------

#: The strict Content-Security-Policy applied to every gateway response that
#: does not set its own. Script stays same-origin; framing is denied twice
#: (CSP frame-ancestors and X-Frame-Options) so a clickjacked phone cannot
#: drive the gateway.
CSP_DEFAULT = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'none';"
)

#: Default per-token request budget per rolling minute window. A stolen
#: token can probe, but it cannot saturate the agent.
TOKEN_RATE_LIMIT_PER_MINUTE = 240


def build_security_headers(*, tls_enabled: bool, existing: dict | None = None) -> dict:
    """The gateway's security header set as a pure, stdlib-testable map.

    ``existing`` lets a route-provided Content-Security-Policy win; every
    other header is always applied. HSTS ships only over TLS, exactly when
    it is meaningful.
    """
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "no-referrer-when-downgrade",
    }
    if tls_enabled:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    current = existing or {}
    has_csp = any(str(key).lower() == "content-security-policy" for key in current)
    if not has_csp:
        headers["Content-Security-Policy"] = CSP_DEFAULT
    return headers


class TokenRateLimiter:
    """Fixed-minute-window counter keyed by token (SEC Stage D, G-24).

    Scope enforcement decides WHAT a token may do; this limiter decides how
    OFTEN. Limits apply per token, so one abused credential cannot starve
    the owner's other devices.
    """

    def __init__(self, per_minute: int = TOKEN_RATE_LIMIT_PER_MINUTE) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be at least 1")
        self.per_minute = int(per_minute)
        self._buckets: dict[tuple[str, int], int] = {}

    def check(self, token: str, *, now: float | None = None) -> bool:
        """Record one request; True while inside the budget."""
        stamp = time.time() if now is None else now
        minute = int(stamp // 60)
        stale = [key for key in self._buckets if key[1] != minute]
        for key in stale:
            del self._buckets[key]
        key = (str(token), minute)
        used = self._buckets.get(key, 0) + 1
        self._buckets[key] = used
        return used <= self.per_minute

    def remaining(self, token: str, *, now: float | None = None) -> int:
        stamp = time.time() if now is None else now
        minute = int(stamp // 60)
        used = self._buckets.get((str(token), minute), 0)
        return max(0, self.per_minute - used)

    def reset(self) -> None:
        self._buckets.clear()


#: Authentication-attempt budget per source per rolling minute. This runs
#: before token verification, so invalid guesses are throttled too.
AUTH_ATTEMPTS_PER_MINUTE = 10


class AuthAttemptLimiter:
    """Fixed-minute-window counter keyed by source address."""

    def __init__(self, per_minute: int = AUTH_ATTEMPTS_PER_MINUTE) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be at least 1")
        self.per_minute = int(per_minute)
        self._buckets: dict[tuple[str, int], int] = {}

    def check(self, key: str, *, now: float | None = None) -> bool:
        """Record one attempt; True while inside the budget."""
        stamp = time.time() if now is None else now
        minute = int(stamp // 60)
        stale = [entry for entry in self._buckets if entry[1] != minute]
        for entry in stale:
            del self._buckets[entry]
        bucket = (str(key), minute)
        used = self._buckets.get(bucket, 0) + 1
        self._buckets[bucket] = used
        return used <= self.per_minute

    def reset(self) -> None:
        self._buckets.clear()


# ---------------------------------------------------------------------------
# mDNS / Bonjour discovery
# ---------------------------------------------------------------------------


class MDNSAdvertiser:
    """Advertise the gateway via mDNS/Bonjour as ``dream.local``.

    Falls back to printing the IP address if the ``avahi`` or ``bonjour``
    tools are not available.
    """

    SERVICE_TYPE = "_dream._tcp"
    SERVICE_NAME = "Dream Gateway"

    def __init__(self, port: int = 9090) -> None:
        self._port = port
        self._process: subprocess.Popen[bytes] | None = None
        self._running = False

    def start(self) -> bool:
        """Start advertising. Returns True if mDNS advertising was started."""
        if platform.system() == "Darwin":
            return self._start_dns_sd()
        return self._start_avahi()

    def stop(self) -> None:
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def _start_dns_sd(self) -> bool:
        """Use macOS ``dns-sd`` command."""
        try:
            self._process = subprocess.Popen(
                [
                    "dns-sd",
                    "-R",
                    self.SERVICE_NAME,
                    "_dream._tcp",
                    "local",
                    str(self._port),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._running = True
            return True
        except FileNotFoundError:
            logger.info("dns-sd not available; mDNS advertising disabled")
            return False

    def _start_avahi(self) -> bool:
        """Use avahi on Linux."""
        try:
            self._process = subprocess.Popen(
                [
                    "avahi-publish-service",
                    self.SERVICE_NAME,
                    "_dream._tcp",
                    str(self._port),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._running = True
            return True
        except FileNotFoundError:
            logger.info("avahi-publish-service not available; mDNS advertising disabled")
            return False

    @staticmethod
    def get_ip_addresses() -> list[str]:
        """Get LAN IP addresses for manual connection."""
        ips: list[str] = []
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                addr = info[4][0]
                if addr and not addr.startswith("127."):
                    ips.append(addr)
        except Exception:
            pass
        return ips


# ---------------------------------------------------------------------------
# Self-signed TLS certificate
# ---------------------------------------------------------------------------


class TLSCertificateManager:
    """Manage TLS certificates for the gateway.

    Generates a self-signed certificate on first use, or can be configured
    with Let's Encrypt for custom domains.
    """

    def __init__(self, cert_dir: str | None = None) -> None:
        self._cert_dir = Path(
            cert_dir or os.path.expanduser("~/.dream/gateway-certs")
        )
        self._cert_dir.mkdir(parents=True, exist_ok=True)

    def get_or_create_self_signed(
        self,
    ) -> tuple[str, str] | None:
        """Get or create a self-signed certificate.

        Returns ``(cert_path, key_path)`` or ``None`` if generation fails.
        """
        cert_path = self._cert_dir / "cert.pem"
        key_path = self._cert_dir / "key.pem"

        if cert_path.exists() and key_path.exists():
            return str(cert_path), str(key_path)

        # Generate self-signed certificate using Python's ssl or openssl.
        try:
            return self._generate_certificate(cert_path, key_path)
        except Exception as exc:
            logger.warning("Failed to generate self-signed cert: %s", exc)
            return None

    def _generate_certificate(
        self, cert_path: Path, key_path: Path
    ) -> tuple[str, str]:
        """Generate a self-signed certificate using openssl."""
        # Build subject.
        hostname = socket.gethostname()

        # Generate key and cert using openssl.
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:4096",
                "-keyout", str(key_path),
                "-out", str(cert_path),
                "-days", "3650",
                "-nodes",
                "-subj", f"/CN={hostname}/O=Dream Gateway",
                "-addext", (
                    f"subjectAltName=DNS:{hostname},"
                    "DNS:dream.local,DNS:localhost,IP:127.0.0.1"
                ),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return str(cert_path), str(key_path)


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------


class GatewayConfig:
    """Configuration for the web gateway.

    The gateway is local-first by construction: the default bind is
    ``127.0.0.1`` and LAN exposure requires an explicit private address with
    ``lan_only`` enabled. ``resolve_gateway_bind`` enforces this policy at
    startup; ``lan_only`` on this object is therefore a verified policy value,
    not a display-only flag.
    """

    def __init__(self) -> None:
        self.enabled: bool = True
        self.port: int = int(os.environ.get("DREAM_GATEWAY_PORT", "9090"))
        self.host: str = os.environ.get("DREAM_GATEWAY_HOST", "127.0.0.1")
        self.tls_enabled: bool = os.environ.get("DREAM_GATEWAY_TLS", "false").lower() in (
            "1", "true", "yes"
        )
        self.lan_only: bool = os.environ.get("DREAM_GATEWAY_LAN_ONLY", "true").lower() in (
            "1", "true", "yes"
        )
        self.read_only: bool = False  # Set per-session via token scope
        self.mdns_enabled: bool = True
        self.allowed_origins: list[str] = _parse_allowed_origins()


def _parse_allowed_origins() -> list[str]:
    """Parse ``DREAM_GATEWAY_ALLOWED_ORIGINS`` (comma-separated)."""
    raw = os.environ.get("DREAM_GATEWAY_ALLOWED_ORIGINS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Bind and origin policy
# ---------------------------------------------------------------------------

GATEWAY_DEFAULT_HOST = "127.0.0.1"
GATEWAY_DEFAULT_PORT = 9090


def classify_gateway_host(host: str) -> str:
    """Classify a bind host as ``loopback``, ``lan`` or refuse it."""
    text = (host or "").strip()
    if not text:
        raise ValueError(
            _bilingual(
                "bind host must be a non-empty address",
                "\u0646\u0634\u0627\u0646\u06cc \u0627\u062a\u0635\u0627\u0644 "
                "\u0646\u0628\u0627\u06cc\u062f \u062e\u0627\u0644\u06cc \u0628\u0627\u0634\u062f",
            )
        )
    if text in {"localhost", "::1"}:
        return "loopback"
    try:
        addr = ipaddress.ip_address(text)
    except ValueError as exc:
        raise ValueError(
            _bilingual(
                f"invalid bind host: {text}",
                "\u0646\u0634\u0627\u0646\u06cc \u0627\u062a\u0635\u0627\u0644 "
                "\u0646\u0627\u0645\u0639\u062a\u0628\u0631: {text}",
            )
        ) from exc
    if addr.is_loopback:
        return "loopback"
    if addr.is_private and not addr.is_unspecified:
        return "lan"
    raise ValueError(
        _bilingual(
            "WAN / public bind is refused. Use 127.0.0.1 or --lan with a private RFC1918 address.",
            "\u0627\u062a\u0635\u0627\u0644 \u0639\u0645\u0648\u0645\u06cc "
            "\u0631\u062f \u0634\u062f. \u0627\u0632 127.0.0.1 \u06cc\u0627 --lan "
            "\u0628\u0627 \u0646\u0634\u0627\u0646\u06cc "
            "\u062e\u0635\u0648\u0635\u06cc "
            "\u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f.",
        )
    )


def resolve_gateway_bind(
    *, lan: bool = False, host: str | None = None, port: int | None = None
) -> dict[str, object]:
    """Return a validated gateway bind record; never a public address."""
    listen_port = GATEWAY_DEFAULT_PORT if port is None else int(port)
    if not 1024 <= listen_port <= 65535:
        raise ValueError(
            _bilingual(
                "port must be between 1024 and 65535",
                "\u067e\u0648\u0631\u062a \u0628\u0627\u06cc\u062f \u0628\u06cc\u0646 "
                "\u06f1\u06f0\u06f2\u06f4 \u0648 \u06f6\u06f5\u06f5\u06f3\u06f5 "
                "\u0628\u0627\u0634\u062f",
            )
        )
    if host:
        kind = classify_gateway_host(host)
        if kind == "lan" and not lan:
            raise ValueError(
                _bilingual(
                    "LAN bind requires --lan",
                    "\u0627\u062a\u0635\u0627\u0644 \u0628\u0647 "
                    "\u0634\u0628\u06a9\u0647\u0654 \u0645\u062d\u0644\u06cc "
                    "\u0646\u06cc\u0627\u0632 \u0628\u0647 --lan \u062f\u0627\u0631\u062f",
                )
            )
        return {
            "host": host.strip(),
            "port": listen_port,
            "kind": kind,
            "leaves_machine": kind != "loopback",
        }
    if lan:
        raise ValueError(
            _bilingual(
                "--lan requires an explicit private host (for example 192.168.1.10)",
                "--lan \u0628\u0647 \u06cc\u06a9 \u0646\u0634\u0627\u0646\u06cc "
                "\u062e\u0635\u0648\u0635\u06cc \u0635\u0631\u06cc\u062d "
                "\u0646\u06cc\u0627\u0632 \u062f\u0627\u0631\u062f "
                "(\u0645\u062b\u0644\u0627\u064b 192.168.1.10)",
            )
        )
    return {
        "host": GATEWAY_DEFAULT_HOST,
        "port": listen_port,
        "kind": "loopback",
        "leaves_machine": False,
    }


gateway_config = GatewayConfig()
token_manager = TokenManager()
tls_manager = TLSCertificateManager()
mdns = MDNSAdvertiser()

# Track active connections.
active_connections: dict[str, dict[str, Any]] = {}


def create_gateway_app(
    config: GatewayConfig | None = None,
    tokens: TokenManager | None = None,
) -> Any:
    """Create and return the FastAPI application.

    Call this from the bridge or standalone entry point.
    """
    cfg = config or gateway_config
    tm = tokens or token_manager

    # Fail closed on a broken token store. Never silently mint a full-access
    # token after a load/migration failure.
    if getattr(tm, "load_error", None):
        raise GatewayTokenStoreError(str(tm.load_error))

    # Enforce local-first bind policy before the listener is constructed.
    bind = resolve_gateway_bind(lan=cfg.lan_only, host=cfg.host, port=cfg.port)
    cfg.host = str(bind["host"])
    cfg.port = int(bind["port"])
    cfg.lan_only = bind["kind"] != "lan"

    # Lazy-import FastAPI so it's optional at the package level.
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, JSONResponse
    except ImportError as exc:
        raise ImportError(
            "FastAPI is required for the web gateway. "
            "Install it with: pip install fastapi uvicorn"
        ) from exc

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        logger.info(
            "Gateway starting on %s:%s (TLS: %s, LAN-only: %s)",
            cfg.host, cfg.port, cfg.tls_enabled, cfg.lan_only,
        )
        if cfg.mdns_enabled and cfg.host != GATEWAY_DEFAULT_HOST:
            mdns.start()
        yield
        # Shutdown
        mdns.stop()

    app = FastAPI(
        title="Dream Gateway",
        version="1.0.0",
        description="Remote access interface for Dream AI assistant",
        lifespan=lifespan,
    )

    # CORS — no credentials by default and no wildcard origin. Browser clients
    # use the same origin that serves the SPA; cross-origin reads are refused
    # unless the owner explicitly configures DREAM_GATEWAY_ALLOWED_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins or [],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Security headers middleware (SEC Stage D, G-23: policy lives in the
    # pure build_security_headers(), pinned by tests).
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Any):
        response = await call_next(request)
        for key, value in build_security_headers(
            tls_enabled=cfg.tls_enabled, existing=dict(response.headers)
        ).items():
            response.headers[key] = value
        return response

    # --- Verification dependency ---

    # SEC Stage D (G-24): per-token rate limiting — a stolen token can probe,
    # never saturate. Auth-attempt limiting runs BEFORE verification so invalid
    # guesses are throttled too.
    rate_limiter = TokenRateLimiter()
    auth_limiter = AuthAttemptLimiter()

    async def _json_body(request: Request) -> dict[str, Any]:
        """Read a bounded JSON object body; reject malformed or oversized data."""
        declared = 0
        length_header = request.headers.get("Content-Length") or ""
        try:
            declared = int(length_header)
        except ValueError:
            declared = GATEWAY_BODY_CAP + 1
        if declared > GATEWAY_BODY_CAP:
            raise HTTPException(status_code=413, detail="Request body exceeds the 64 KiB cap")
        raw = await request.body()
        if len(raw) > GATEWAY_BODY_CAP:
            raise HTTPException(status_code=413, detail="Request body exceeds the 64 KiB cap")
        if not raw:
            raise HTTPException(status_code=400, detail="Request body is required")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Request body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")
        return payload

    async def _preflight(request: Request):
        if _query_token_present(request):
            raise HTTPException(
                status_code=400,
                detail="tokens in the query string are refused",
            )
        if not _origin_allowed(request, cfg):
            raise HTTPException(status_code=403, detail="Cross-origin request refused")
        ip = request.client.host if request.client else "unknown"
        if not auth_limiter.check(ip, now=time.time()):
            raise HTTPException(status_code=429, detail="Too many authentication attempts")

    async def verify_read_token(request: Request):
        await _preflight(request)
        token = _extract_token(request)
        if token is None:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        info = tm.verify_token(token, TokenScope.READ)
        if info is None:
            raise HTTPException(status_code=403, detail="Invalid or insufficient token")
        if not rate_limiter.check(token):
            raise HTTPException(status_code=429, detail="Token rate limit exceeded")
        request.state.token_scope = info["scope"]
        request.state.token_info = info
        return token

    async def verify_write_token(request: Request):
        await _preflight(request)
        token = _extract_token(request)
        if token is None:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        info = tm.verify_token(token, TokenScope.WRITE)
        if info is None:
            raise HTTPException(status_code=403, detail="Write access required")
        if not rate_limiter.check(token):
            raise HTTPException(status_code=429, detail="Token rate limit exceeded")
        request.state.token_scope = info["scope"]
        request.state.token_info = info
        return token

    # --- Routes ---

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "1.0.0",
            "uptime_seconds": time.time() - _get_start_time(),
        }

    @app.get("/api/gateway/status")
    async def gateway_status(token: str = Depends_safe(verify_read_token)):
        """Return gateway status and active connections."""
        return {
            "enabled": cfg.enabled,
            "port": cfg.port,
            "tls": cfg.tls_enabled,
            "lan_only": cfg.lan_only,
            "connections": len(active_connections),
            "active_connections": [
                {
                    "id": cid,
                    "ip": info.get("ip", "unknown"),
                    "device": info.get("device", "unknown"),
                    "scope": info.get("scope", "read"),
                    "connected_at": info.get("connected_at"),
                }
                for cid, info in active_connections.items()
            ],
        }

    @app.post("/api/gateway/token/rotate")
    async def rotate_token(
        request: Request,
        token: str = Depends_safe(verify_write_token),
    ):
        """Rotate the current token."""
        new_token = tm.rotate_token(token)
        if new_token is None:
            raise HTTPException(status_code=404, detail="Token not found")
        return {"token": new_token, "scope": "write"}

    @app.post("/api/gateway/token/create")
    async def create_token_endpoint(
        request: Request,
        token: str = Depends_safe(verify_write_token),
    ):
        """Create a new token with specified scope; returns the raw value once."""
        body = await _json_body(request)
        scope_str = str(body.get("scope", "read"))
        label = str(body.get("label", "New Token"))
        if scope_str == "write":
            scope = TokenScope.WRITE
        elif scope_str == "read":
            scope = TokenScope.READ
        else:
            raise HTTPException(status_code=400, detail="scope must be 'read' or 'write'")
        if len(label) > 200:
            raise HTTPException(status_code=400, detail="label must be at most 200 characters")
        new_token = tm.create_token(scope=scope, label=label)
        return {"token": new_token, "scope": scope.value, "label": label}

    @app.get("/api/gateway/tokens")
    async def list_tokens(
        token: str = Depends_safe(verify_write_token),
    ):
        """List token metadata only (never raw values or verifiers)."""
        return {"tokens": tm.list_tokens()}

    @app.post("/api/gateway/token/revoke")
    async def revoke_token_endpoint(
        request: Request,
        token: str = Depends_safe(verify_write_token),
    ):
        """Revoke a token by full raw value or non-secret id."""
        body = await _json_body(request)
        token_to_revoke = str(body.get("token", "")).strip()
        if not token_to_revoke:
            raise HTTPException(status_code=400, detail="token is required")
        if tm.revoke_token(token_to_revoke):
            return {"revoked": True}
        raise HTTPException(status_code=404, detail="Token not found")

    @app.get("/api/gateway/connections")
    async def list_connections(
        token: str = Depends_safe(verify_read_token),
    ):
        """List active gateway connections."""
        return {
            "connections": [
                {
                    "id": cid,
                    "ip": info.get("ip", "unknown"),
                    "device": info.get("device", "unknown"),
                    "scope": info.get("scope", "read"),
                    "user_agent": info.get("user_agent", "unknown"),
                    "connected_at": info.get("connected_at"),
                }
                for cid, info in active_connections.items()
            ]
        }

    @app.post("/api/gateway/connections/{connection_id}/disconnect")
    async def disconnect_connection(
        connection_id: str,
        token: str = Depends_safe(verify_write_token),
    ):
        """Disconnect a specific client."""
        if connection_id in active_connections:
            del active_connections[connection_id]
            return {"disconnected": True}
        raise HTTPException(status_code=404, detail="Connection not found")

    @app.post("/api/gateway/config")
    async def update_config(
        request: Request,
        token: str = Depends_safe(verify_write_token),
    ):
        """Update in-memory gateway metadata (bind stays fixed at startup)."""
        body = await _json_body(request)
        for key in ("enabled", "lan_only", "tls_enabled"):
            if key in body and not isinstance(body[key], bool):
                raise HTTPException(status_code=400, detail=f"{key} must be a boolean")
        if "enabled" in body:
            cfg.enabled = bool(body["enabled"])
        if "lan_only" in body:
            cfg.lan_only = bool(body["lan_only"])
        if "tls_enabled" in body:
            cfg.tls_enabled = bool(body["tls_enabled"])
        return {"saved": True, "config": _config_to_dict(cfg)}

    # Serve UI (React SPA) — adjust the path to the actual build.
    @app.get("/")
    @app.get("/{path:path}")
    async def serve_ui(path: str = ""):
        """Serve the React SPA."""
        ui_dir = _find_ui_dir()
        if not ui_dir:
            return JSONResponse(
                content={
                    "error": "UI build not found. Build the desktop app first.",
                    "hint": "Run: cd apps/desktop && npm run build",
                },
                status_code=501,
            )

        # Serve index.html for all non-API routes.
        file_path = ui_dir / "index.html"
        if file_path.exists():
            return FileResponse(str(file_path))
        return JSONResponse(
            content={"error": "UI not available"},
            status_code=501,
        )

    # --- Connection tracking middleware ---

    @app.middleware("http")
    async def track_connection(request: Request, call_next: Any):
        if request.url.path.startswith("/api/"):
            # Track the connection.
            conn_id = uuid.uuid4().hex[:12]
            ip = request.client.host if request.client else "unknown"
            active_connections[conn_id] = {
                "ip": ip,
                "device": request.headers.get("User-Agent", "unknown"),
                "scope": getattr(request.state, "token_scope", "unknown"),
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "connected_at": time.time(),
            }
            try:
                response = await call_next(request)
                return response
            finally:
                active_connections.pop(conn_id, None)
        else:
            return await call_next(request)

    return app


# --- Helper functions ---


#: Maximum request body accepted by the authenticated JSON routes.
GATEWAY_BODY_CAP = 64 * 1024


def _extract_token(request: Any) -> str | None:
    """Extract a bearer token from ``Authorization`` only.

    Query-string and header-based token credentials are intentionally not
    accepted; they can appear in URLs, logs, referrers, and screenshots.
    """
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _query_token_present(request: Any) -> bool:
    """True when a credential-bearing ``?token=`` parameter is present."""
    return "token" in (getattr(request, "query_params", {}) or {})


def gateway_origins(cfg: GatewayConfig) -> set[str]:
    """Origins this gateway accepts in the ``Origin`` header."""
    scheme = "https" if cfg.tls_enabled else "http"
    origins = {f"{scheme}://{cfg.host}:{cfg.port}"}
    if cfg.host in {"127.0.0.1", "localhost", "::1"}:
        origins.add(f"{scheme}://127.0.0.1:{cfg.port}")
        origins.add(f"{scheme}://localhost:{cfg.port}")
    origins.update(item.rstrip("/") for item in cfg.allowed_origins)
    return origins


def _origin_allowed(request: Any, cfg: GatewayConfig) -> bool:
    """Allow non-browser requests and same-origin/allow-listed browser requests."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return origin.strip().rstrip("/") in gateway_origins(cfg)


def _find_ui_dir() -> Path | None:
    """Locate the built React UI directory."""
    candidates = [
        Path("apps/desktop/dist"),
        Path("../apps/desktop/dist"),
        Path(os.path.expanduser("~/.dream/ui")),
    ]
    for c in candidates:
        if c.exists() and (c / "index.html").exists():
            return c.resolve()
    return None


def _config_to_dict(cfg: GatewayConfig) -> dict[str, Any]:
    return {
        "enabled": cfg.enabled,
        "port": cfg.port,
        "host": cfg.host,
        "tls_enabled": cfg.tls_enabled,
        "lan_only": cfg.lan_only,
        "mdns_enabled": cfg.mdns_enabled,
    }


_start_time: float = time.time()


def _get_start_time() -> float:
    return _start_time


# FastAPI doesn't support Depends_safe naturally; we use a wrapper.
# We define a helper that the route dependencies use.
def Depends_safe(dep: Any) -> Any:
    """Marker for FastAPI dependency (passthrough)."""
    from fastapi import Depends

    return Depends(dep)


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def run_gateway(
    host: str | None = None,
    port: int = GATEWAY_DEFAULT_PORT,
    tls: bool = False,
    *,
    lan: bool = False,
    log_level: str = "info",
) -> None:
    """Run the gateway server standalone.

    The bind is validated through :func:`resolve_gateway_bind` before the
    listener is created; public and unspecified addresses are refused.
    """
    bind = resolve_gateway_bind(lan=lan, host=host, port=port)
    cfg = gateway_config
    cfg.host = str(bind["host"])
    cfg.port = int(bind["port"])
    cfg.tls_enabled = tls
    cfg.lan_only = bind["kind"] == "loopback"

    try:
        app = create_gateway_app(cfg)
    except (GatewayTokenStoreError, ValueError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError("uvicorn is required. Install with: pip install uvicorn") from exc

    ssl_cert = None
    ssl_key = None
    if tls:
        certs = tls_manager.get_or_create_self_signed()
        if certs:
            ssl_cert, ssl_key = certs

    print(f"🌐 Dream Gateway listening on http{'s' if tls else ''}://{cfg.host}:{cfg.port}")
    print("🔑 Create a token once in the desktop settings; it is never printed here.")

    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        ssl_certfile=ssl_cert,
        ssl_keyfile=ssl_key,
        log_level=log_level,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dream Web Gateway")
    parser.add_argument("--host", default=None, help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=GATEWAY_DEFAULT_PORT, help="Port")
    parser.add_argument("--lan", action="store_true", help="Allow a private RFC1918 bind host")
    parser.add_argument("--tls", action="store_true", help="Enable TLS")
    parser.add_argument(
        "--log-level", default="info", help="Logging level"
    )
    args = parser.parse_args()
    run_gateway(
        host=args.host,
        port=args.port,
        tls=args.tls,
        lan=args.lan,
        log_level=args.log_level,
    )


__all__ = [
    "GatewayConfig",
    "TokenManager",
    "TokenScope",
    "MDNSAdvertiser",
    "TLSCertificateManager",
    "create_gateway_app",
    "run_gateway",
    "gateway_config",
    "token_manager",
    "tls_manager",
    "mdns",
]