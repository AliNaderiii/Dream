"""Stdlib JSON-RPC façade. Bearer only. Query-string tokens refused."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from dream.reliability import Deadline
from dream.remotegw.errors import RemoteGwError, RemoteGwSecurityError
from dream.remotegw.tokens import RemoteTokens

BODY_CAP = 65_536
READ_METHODS = frozenset({"health", "remotegw.status", "remotegw.health"})


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def extract_bearer(headers: Any, query: dict[str, list[str]]) -> str:
    if "token" in query:
        raise RemoteGwSecurityError(
            _bilingual(
                "tokens in the query string are refused",
                "توکن در query string رد می‌شود",
            )
        )
    auth = ""
    if hasattr(headers, "get"):
        auth = headers.get("Authorization") or headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise RemoteGwSecurityError(
            _bilingual("Authorization: Bearer is required", "هدر Authorization: Bearer لازم است")
        )
    return auth[7:].strip()


class RemoteGwHandler(BaseHTTPRequestHandler):
    server_version = "DreamRemote/0.4.4"
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:
        message = fmt % args
        if "drm_" in message or "Bearer" in message:
            return

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path in {"/health", "/"}:
            if "token" in query:
                self._send(
                    400,
                    {
                        "error": _bilingual(
                            "tokens in the query string are refused",
                            "توکن در query string رد می‌شود",
                        )
                    },
                )
                return
            self._send(200, {"status": "ok", "service": "dream-remotegw"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path != "/rpc":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > BODY_CAP:
            self._send(
                413,
                {
                    "error": _bilingual(
                        "request body must be between 1 and 65536 bytes",
                        "بدنهٔ درخواست باید بین ۱ و ۶۵۵۳۶ بایت باشد",
                    )
                },
            )
            return
        deadline = Deadline.after(8.0, owner="remotegw", step="rpc")
        raw = self.rfile.read(length)
        deadline.throw_if_exceeded()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            self._rpc_error(None, 400, -32700, "parse error")
            return
        if not isinstance(payload, dict):
            self._rpc_error(None, 400, -32600, "invalid request")
            return
        req_id = payload.get("id")
        method = payload.get("method")
        tokens: RemoteTokens = self.server.tokens  # type: ignore[attr-defined]
        try:
            secret = extract_bearer(self.headers, query)
            need = "read" if method in READ_METHODS else "admin"
            tokens.verify(secret, need=need)
            if method in {"health", "remotegw.health"}:
                result = {"status": "ok", "service": "dream-remotegw"}
            elif method == "remotegw.status":
                result = dict(self.server.status)  # type: ignore[attr-defined]
            else:
                raise RemoteGwError(
                    _bilingual(f"unknown method {method}", f"روش ناشناخته {method}")
                )
            self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": result})
        except RemoteGwSecurityError as exc:
            self._rpc_error(req_id, 403, -32002, str(exc))
        except RemoteGwError as exc:
            self._rpc_error(req_id, 400, -32601, str(exc))
        except Exception:
            self._rpc_error(req_id, 500, -32603, "internal error")

    def _rpc_error(self, req_id: Any, http: int, code: int, message: str) -> None:
        error = {"code": code, "message": message}
        self._send(http, {"jsonrpc": "2.0", "id": req_id, "error": error})


class RemoteGwServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, bind: dict[str, object], tokens: RemoteTokens) -> None:
        super().__init__((str(bind["host"]), int(bind["port"])), RemoteGwHandler)
        self.tokens = tokens
        self.status = {
            "bind": bind,
            "running": True,
            "auth": "bearer",
            "query_tokens": False,
        }

    def server_bind(self) -> None:
        self.timeout = 2.0
        super().server_bind()
