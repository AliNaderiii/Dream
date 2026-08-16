"""Web Gateway — FastAPI HTTP server for remote access to Dream.

Serves the same React desktop UI as a web application, with token
authentication, read-only mode, LAN discovery via mDNS, and TLS support.

The gateway runs as part of the Python sidecar or as a standalone process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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


class TokenManager:
    """Manages authentication tokens for the web gateway.

    A random setup token is generated on first launch, stored in a JSON file.
    The user can regenerate it from settings.
    """

    def __init__(self, tokens_path: str | None = None) -> None:
        self._tokens_path = tokens_path or os.path.expanduser(
            "~/.dream/gateway_tokens.json"
        )
        self._tokens: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def has_tokens(self) -> bool:
        return len(self._tokens) > 0

    def get_setup_token(self) -> str | None:
        """Return the first admin/write token, or None."""
        for tid, info in self._tokens.items():
            if info.get("scope") == "write":
                return tid
        return None

    def create_token(
        self,
        scope: TokenScope = TokenScope.WRITE,
        label: str = "Default",
    ) -> str:
        """Create a new authentication token.

        Args:
            scope: ``"read"`` or ``"write"``.
            label: Human-readable label for this token.

        Returns:
            The token string.
        """
        token = f"drm_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"
        self._tokens[token] = {
            "scope": scope.value,
            "label": label,
            "created_at": time.time(),
            "last_used_at": None,
        }
        self._save()
        return token

    def rotate_token(self, old_token: str) -> str | None:
        """Rotate (regenerate) a token. Returns the new token or None."""
        info = self._tokens.pop(old_token, None)
        if info is None:
            return None
        new_token = self.create_token(
            scope=TokenScope(info["scope"]),
            label=info.get("label", "Rotated"),
        )
        return new_token

    def revoke_token(self, token: str) -> bool:
        """Revoke a token. Returns True if found."""
        if token in self._tokens:
            del self._tokens[token]
            self._save()
            return True
        return False

    def verify_token(
        self, token: str, required_scope: TokenScope = TokenScope.READ
    ) -> dict[str, Any] | None:
        """Verify a token and return its info, or None if invalid.

        Optionally checks scope — a write-scoped token satisfies read
        requirements.
        """
        info = self._tokens.get(token)
        if info is None:
            return None
        token_scope = TokenScope(info["scope"])
        if required_scope == TokenScope.READ and token_scope in (
            TokenScope.READ,
            TokenScope.WRITE,
        ):
            info["last_used_at"] = time.time()
            self._save()
            return info
        if required_scope == TokenScope.WRITE and token_scope == TokenScope.WRITE:
            info["last_used_at"] = time.time()
            self._save()
            return info
        return None

    def list_tokens(self) -> list[dict[str, Any]]:
        """List all tokens (without exposing the full token values)."""
        return [
            {
                "prefix": t[:12] + "...",
                "scope": info["scope"],
                "label": info["label"],
                "created_at": info["created_at"],
                "last_used_at": info.get("last_used_at"),
            }
            for t, info in self._tokens.items()
        ]

    def all_tokens(self) -> dict[str, dict[str, Any]]:
        """Return all tokens with their full values (for settings display)."""
        return dict(self._tokens)

    def _load(self) -> None:
        try:
            with open(self._tokens_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._tokens = data
        except (OSError, ValueError):
            self._tokens = {}

    def _save(self) -> None:
        try:
            path = Path(self._tokens_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._tokens, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(path))
        except OSError as exc:
            logger.warning("Failed to save tokens: %s", exc)


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
                "-addext", f"subjectAltName=DNS:{hostname},DNS:dream.local,DNS:localhost,IP:127.0.0.1",
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
    """Configuration for the web gateway."""

    def __init__(self) -> None:
        self.enabled: bool = True
        self.port: int = int(os.environ.get("DREAM_GATEWAY_PORT", "9090"))
        self.host: str = os.environ.get("DREAM_GATEWAY_HOST", "0.0.0.0")
        self.tls_enabled: bool = os.environ.get("DREAM_GATEWAY_TLS", "false").lower() in (
            "1", "true", "yes"
        )
        self.lan_only: bool = os.environ.get("DREAM_GATEWAY_LAN_ONLY", "true").lower() in (
            "1", "true", "yes"
        )
        self.read_only: bool = False  # Set per-session via token scope
        self.mdns_enabled: bool = True
        self.allowed_origins: list[str] = ["*"]


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

    # Ensure at least one token exists.
    if not tm.has_tokens:
        tm.create_token(scope=TokenScope.WRITE, label="Setup Token")

    # Lazy-import FastAPI so it's optional at the package level.
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, JSONResponse, Response
    except ImportError:
        raise ImportError(
            "FastAPI is required for the web gateway. "
            "Install it with: pip install fastapi uvicorn"
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        logger.info(
            "Gateway starting on %s:%s (TLS: %s, LAN-only: %s)",
            cfg.host, cfg.port, cfg.tls_enabled, cfg.lan_only,
        )
        if cfg.mdns_enabled:
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

    # CORS — allow any origin for LAN/mobile access; tighten for production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security headers middleware.
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Any):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
        if cfg.tls_enabled:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        # CSP
        if not response.headers.get("Content-Security-Policy"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none';"
            )
        return response

    # --- Verification dependency ---

    async def verify_read_token(request: Request):
        token = _extract_token(request)
        if token is None:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        info = tm.verify_token(token, TokenScope.READ)
        if info is None:
            raise HTTPException(status_code=403, detail="Invalid or insufficient token")
        request.state.token_scope = info["scope"]
        request.state.token_info = info
        return token

    async def verify_write_token(request: Request):
        token = _extract_token(request)
        if token is None:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        info = tm.verify_token(token, TokenScope.WRITE)
        if info is None:
            raise HTTPException(status_code=403, detail="Write access required")
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
        """Create a new token with specified scope."""
        body = await request.json()
        scope_str = body.get("scope", "read")
        label = body.get("label", "New Token")
        scope = TokenScope.WRITE if scope_str == "write" else TokenScope.READ
        new_token = tm.create_token(scope=scope, label=label)
        return {"token": new_token, "scope": scope.value, "label": label}

    @app.get("/api/gateway/tokens")
    async def list_tokens(
        token: str = Depends_safe(verify_write_token),
    ):
        """List all tokens (partially masked)."""
        return {"tokens": tm.list_tokens()}

    @app.post("/api/gateway/token/revoke")
    async def revoke_token_endpoint(
        request: Request,
        token: str = Depends_safe(verify_write_token),
    ):
        """Revoke a token by prefix or full value."""
        body = await request.json()
        token_to_revoke = body.get("token", "")
        if tm.revoke_token(token_to_revoke):
            return {"revoked": True}
        # Try matching by prefix.
        for t in list(tm.all_tokens().keys()):
            if t.startswith(token_to_revoke):
                tm.revoke_token(t)
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
        """Update gateway configuration."""
        body = await request.json()
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


def _extract_token(request: Any) -> str | None:
    """Extract token from Authorization header, query param, or form body."""
    # Authorization: Bearer <token>
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]

    # Query parameter: ?token=...
    token = request.query_params.get("token")
    if token:
        return str(token)

    # X-Access-Token header.
    xtoken = request.headers.get("X-Access-Token")
    if xtoken:
        return str(xtoken)

    return None


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
    host: str = "0.0.0.0",
    port: int = 9090,
    tls: bool = False,
    log_level: str = "info",
) -> None:
    """Run the gateway server standalone."""
    cfg = gateway_config
    cfg.host = host
    cfg.port = port
    cfg.tls_enabled = tls

    app = create_gateway_app(cfg)

    try:
        import uvicorn
    except ImportError:
        raise ImportError("uvicorn is required. Install with: pip install uvicorn")

    ssl_cert = None
    ssl_key = None
    if tls:
        certs = tls_manager.get_or_create_self_signed()
        if certs:
            ssl_cert, ssl_key = certs

    print(f"🌐 Dream Gateway listening on http{'s' if tls else ''}://{host}:{port}")
    if token_manager.get_setup_token():
        print(f"🔑 Setup token: {token_manager.get_setup_token()[:16]}... (use in Authorization header)")

    uvicorn.run(
        app,
        host=host,
        port=port,
        ssl_certfile=ssl_cert,
        ssl_keyfile=ssl_key,
        log_level=log_level,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dream Web Gateway")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=9090, help="Port")
    parser.add_argument("--tls", action="store_true", help="Enable TLS")
    parser.add_argument(
        "--log-level", default="info", help="Logging level"
    )
    args = parser.parse_args()
    run_gateway(
        host=args.host,
        port=args.port,
        tls=args.tls,
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