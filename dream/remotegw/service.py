"""Process-wide remote-gateway controller used by the bridge and CLI."""

from __future__ import annotations

import os
import threading
from typing import Any

from dream.remotegw.bind import resolve_bind
from dream.remotegw.errors import RemoteGwError
from dream.remotegw.http import RemoteGwServer
from dream.remotegw.tokens import RemoteTokens

_DEFAULT_STORE = "data/remotegw_tokens.json"


class RemoteGwService:
    def __init__(self, tokens: RemoteTokens | None = None) -> None:
        path = os.environ.get("DREAM_REMOTEGW_TOKENS", _DEFAULT_STORE)
        self.tokens = tokens or RemoteTokens(path=path)
        self._lock = threading.RLock()
        self._server: RemoteGwServer | None = None
        self._thread: threading.Thread | None = None
        self._bind: dict[str, object] | None = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            bind = self._bind or resolve_bind(lan=False, host=None, port=None)
            return {
                "running": self._server is not None,
                "bind": bind,
                "leaves_machine": bool(bind.get("leaves_machine")),
                "auth": "bearer",
                "query_tokens": False,
                "tokens": self.tokens.list()["tokens"],
            }

    def start(
        self, *, lan: bool = False, host: str | None = None, port: int | None = None
    ) -> dict[str, Any]:
        bind = resolve_bind(lan=lan, host=host, port=port)
        with self._lock:
            if self._server is not None:
                raise RemoteGwError("remote gateway is already running\nدرگاه از قبل در حال اجراست")
            server = RemoteGwServer(bind, self.tokens)
            thread = threading.Thread(
                target=server.serve_forever, name="dream-remotegw", daemon=True
            )
            thread.start()
            self._server = server
            self._thread = thread
            self._bind = bind
        return {"started": True, "bind": bind, "leaves_machine": bind["leaves_machine"]}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            server = self._server
            self._server = None
            self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        return {"stopped": True}

    def issue_token(self, *, scope: str = "read", label: str = "Remote") -> dict[str, Any]:
        return self.tokens.issue(scope=scope, label=label)

    def revoke_token(self, token: str) -> dict[str, Any]:
        return self.tokens.revoke(token)

    def preview(
        self,
        *,
        lan: bool = False,
        host: str | None = None,
        port: int | None = None,
    ) -> dict[str, Any]:
        bind = resolve_bind(lan=lan, host=host, port=port)
        url = f"http://{bind['host']}:{bind['port']}/"
        return {
            "url": url,
            "qr": url,
            "token_in_qr": False,
            "leaves_machine": bind["leaves_machine"],
            "bind": bind,
            "hint_en": "Paste the token once in Authorization: Bearer. It is not in the QR.",
            "hint_fa": "توکن را یک‌بار در Authorization: Bearer بچسبانید. داخل QR نیست.",
        }


_service: RemoteGwService | None = None
_lock = threading.Lock()


def get_service() -> RemoteGwService:
    global _service
    with _lock:
        if _service is None:
            _service = RemoteGwService()
        return _service


def reset_service(service: RemoteGwService | None = None) -> RemoteGwService | None:
    global _service
    with _lock:
        if _service is not None:
            try:
                _service.stop()
            except Exception:
                pass
        _service = service
        return _service
