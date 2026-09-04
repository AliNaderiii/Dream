"""Token presentation on top of TokenManager. Never logs the secret."""

from __future__ import annotations

import os
from typing import Any

from dream.gateway_server import TokenManager, TokenScope
from dream.remotegw.errors import RemoteGwSecurityError

FINE_SCOPES = ("read", "chat", "safe_tools", "admin")
_WRITE_SCOPES = frozenset({"chat", "safe_tools", "admin"})


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def mask_token(token: str) -> str:
    if not token or len(token) < 12:
        return "drm_***"
    return token[:12] + "..."


def coarse_scope(fine: str) -> TokenScope:
    key = (fine or "").strip().lower()
    if key not in FINE_SCOPES:
        raise RemoteGwSecurityError(
            _bilingual(f"unknown scope {fine!r}", f"سطح دسترسی ناشناخته {fine!r}")
        )
    return TokenScope.WRITE if key in _WRITE_SCOPES else TokenScope.READ


class RemoteTokens:
    """Create / list / revoke via TokenManager. Fine scopes live in the label."""

    def __init__(self, manager: TokenManager | None = None, path: str | None = None) -> None:
        store = path or os.environ.get("DREAM_REMOTEGW_TOKENS")
        self.manager = manager or TokenManager(tokens_path=store)

    def issue(self, *, scope: str = "read", label: str = "Remote") -> dict[str, Any]:
        fine = (scope or "read").strip().lower()
        coarse = coarse_scope(fine)
        title = f"{label.strip() or 'Remote'} [{fine}]"
        secret = self.manager.create_token(scope=coarse, label=title)
        return {
            "token": secret,
            "prefix": mask_token(secret),
            "scope": fine,
            "coarse": coarse.value,
            "label": title,
            "leaves_machine": False,
        }

    def revoke(self, token: str) -> dict[str, Any]:
        raw = (token or "").strip()
        if not raw:
            raise RemoteGwSecurityError(
                _bilingual("token is required to revoke", "برای ابطال، توکن لازم است")
            )
        ok = self.manager.revoke_token(raw)
        if not ok:
            for row in self.manager.list_tokens():
                if str(row.get("id")) == raw:
                    ok = self.manager.revoke_token(str(row["id"]))
                    break
        if not ok:
            raise RemoteGwSecurityError(
                _bilingual("token not found", "توکن پیدا نشد")
            )
        return {"revoked": True}

    def verify(self, token: str, *, need: str = "read") -> dict[str, Any]:
        raw = (token or "").strip()
        if not raw:
            raise RemoteGwSecurityError(
                _bilingual("missing bearer token", "توکن Bearer نیست")
            )
        required = coarse_scope(need) if need in FINE_SCOPES else TokenScope.READ
        info = self.manager.verify_token(raw, required)
        if info is None:
            raise RemoteGwSecurityError(
                _bilingual(
                    "invalid or insufficient token",
                    "توکن نامعتبر است یا سطح دسترسی کافی نیست",
                )
            )
        label = str(info.get("label") or "")
        fine = "write"
        for name in FINE_SCOPES:
            if f"[{name}]" in label:
                fine = name
                break
        if need in _WRITE_SCOPES and info.get("scope") != "write":
            raise RemoteGwSecurityError(
                _bilingual(
                    "read token cannot perform this action",
                    "توکن فقط‌خواندنی این کار را نمی‌تواند انجام دهد",
                )
            )
        return {
            "scope": info.get("scope"),
            "fine": fine,
            "label": label,
            "prefix": mask_token(raw),
        }

    def list(self) -> dict[str, Any]:
        rows = self.manager.list_tokens()
        return {"tokens": rows, "count": len(rows)}
