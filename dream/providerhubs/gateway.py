"""Optional tool gateway: per-tool toggles, never required for local chat."""

from __future__ import annotations

from typing import Any

from dream.model_providers import KeychainCredentialStore
from dream.providerhubs.types import GATEWAY_TOOLS

GATEWAY_ACCOUNT = "gateway:scoped-token"
GATEWAY_SERVICE = "Dream Tool Gateway"


class ToolGateway:
    """One optional auth for extra tools. Tokens stay in the OS keychain."""

    def __init__(self, credentials: KeychainCredentialStore | None = None) -> None:
        self.credentials = credentials or KeychainCredentialStore()
        self.enabled = False
        self.tools = {
            tool_id: {"id": tool_id, "enabled": False, "byok": True, "credential_configured": False}
            for tool_id in GATEWAY_TOOLS
        }

    def snapshot(self) -> dict[str, Any]:
        configured = False
        try:
            configured = self.credentials.has("tool-gateway", "api_key")
        except Exception:
            configured = False
        tools = []
        for tool_id in GATEWAY_TOOLS:
            row = dict(self.tools[tool_id])
            row["credential_configured"] = bool(configured and row["enabled"])
            tools.append(row)
        return {
            "optional": True,
            "enabled": self.enabled,
            "required_for_local": False,
            "auth": "keychain" if configured else "none",
            "tools": tools,
        }

    def update(
        self,
        *,
        enabled: bool | None = None,
        tool_id: str | None = None,
        tool_enabled: bool | None = None,
        byok: bool | None = None,
    ) -> dict[str, Any]:
        if enabled is not None:
            self.enabled = bool(enabled)
        if tool_id:
            if tool_id not in self.tools:
                raise ValueError(f"unknown gateway tool: {tool_id}")
            if tool_enabled is not None:
                self.tools[tool_id]["enabled"] = bool(tool_enabled)
            if byok is not None:
                self.tools[tool_id]["byok"] = bool(byok)
        return self.snapshot()

    def load_state(self, blob: dict[str, Any]) -> None:
        self.enabled = bool(blob.get("enabled"))
        for row in blob.get("tools") or []:
            if not isinstance(row, dict):
                continue
            tool_id = row.get("id")
            if tool_id not in self.tools:
                continue
            self.tools[tool_id]["enabled"] = bool(row.get("enabled"))
            self.tools[tool_id]["byok"] = bool(row.get("byok", True))

    def dump_state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "tools": [
                {"id": tool_id, "enabled": row["enabled"], "byok": row["byok"]}
                for tool_id, row in self.tools.items()
            ],
        }
