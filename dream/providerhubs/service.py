"""Provider hubs service: catalog, runtimes, diagnostics, and gateway."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from dream.model_providers import KeychainCredentialStore
from dream.providerhubs.adapters import RuntimeAdapter
from dream.providerhubs.gateway import ToolGateway
from dream.providerhubs.types import (
    CATALOG_CLOUD,
    FIX_HINTS,
    LOCAL_PRIVACY_EN,
    LOCAL_PRIVACY_FA,
    PARSER_INFO,
    ROUTE_PRIORITY,
    RUNTIME_IDS,
    RUNTIME_SPECS,
)
from dream.router import resolve_route

Opener = Callable[..., Any]


class ProviderHubsError(ValueError):
    """Invalid provider-hubs input."""


class ProviderHubsService:
    """In-process runtime matrix. Startup never waits on a probe."""

    def __init__(
        self,
        *,
        state_path: str | os.PathLike[str] | None = None,
        opener: Opener = urlopen,
        credentials: KeychainCredentialStore | None = None,
    ) -> None:
        self._opener = opener
        self.gateway = ToolGateway(credentials=credentials)
        self._lock = threading.RLock()
        self._selected: dict[str, str] = {}
        self._models: dict[str, list[str]] = {runtime_id: [] for runtime_id in RUNTIME_IDS}
        self._health: dict[str, str] = {runtime_id: "idle" for runtime_id in RUNTIME_IDS}
        self._endpoints: dict[str, str] = {
            runtime_id: str(RUNTIME_SPECS[runtime_id]["endpoint"]) for runtime_id in RUNTIME_IDS
        }
        default_state = Path.home() / ".dream" / "providerhubs-state.json"
        env_path = (os.environ.get("DREAM_PROVIDERHUBS_STATE") or "").strip()
        self.state_path = Path(state_path or env_path or default_state)
        self._load()

    def adapter(self, runtime_id: str) -> RuntimeAdapter:
        _require_runtime(runtime_id)
        endpoint = self._endpoints[runtime_id]
        adapter = RuntimeAdapter(runtime_id, endpoint=endpoint, opener=self._opener)
        adapter.endpoint = adapter.env_endpoint() if adapter.configured_from_env() else endpoint
        self._endpoints[runtime_id] = adapter.endpoint
        return adapter

    def catalog(self, query: str = "") -> dict[str, Any]:
        entries = [self._catalog_entry(runtime_id) for runtime_id in RUNTIME_IDS]
        entries.extend(dict(item) for item in CATALOG_CLOUD)
        needle = query.strip().lower()
        if needle:
            entries = [
                entry
                for entry in entries
                if needle in entry["id"].lower()
                or needle in entry["name"].lower()
                or needle in entry["notes"].lower()
                or any(needle in runtime for runtime in entry["runtimes"])
            ]
        return {"catalog": entries, "count": len(entries)}

    def runtimes(self) -> dict[str, Any]:
        return {
            "runtimes": [self._runtime_record(runtime_id) for runtime_id in RUNTIME_IDS],
            "recommended": "ollama",
        }

    def health(self, runtime_id: str) -> dict[str, Any]:
        record = self._runtime_record(_require_runtime(runtime_id))
        return {
            "runtime_id": record["id"],
            "health": record["health"],
            "detected": record["detected"],
        }

    def models(self, runtime_id: str) -> dict[str, Any]:
        runtime_id = _require_runtime(runtime_id)
        adapter = self.adapter(runtime_id)
        listed = adapter.list_models()
        if listed:
            self._models[runtime_id] = listed
            if self._selected.get(runtime_id) not in listed:
                self._selected[runtime_id] = listed[0]
            self._persist()
        return {
            "runtime_id": runtime_id,
            "models": list(self._models[runtime_id]),
            "selected_model": self._selected.get(runtime_id, ""),
        }

    def select_model(self, runtime_id: str, model: str) -> dict[str, Any]:
        runtime_id = _require_runtime(runtime_id)
        if not isinstance(model, str) or not model.strip():
            raise ProviderHubsError("model must be a non-empty string")
        known = self._models[runtime_id]
        if model in known:
            self._selected[runtime_id] = model
            self._persist()
        return self._runtime_record(runtime_id)

    def test(self, runtime_id: str) -> dict[str, Any]:
        runtime_id = _require_runtime(runtime_id)
        result = self.adapter(runtime_id).health()
        self._health[runtime_id] = "healthy" if result["ok"] else "down"
        if result["ok"]:
            listed = self.adapter(runtime_id).list_models()
            if listed:
                self._models[runtime_id] = listed
                self._selected.setdefault(runtime_id, listed[0])
        self._persist()
        return {
            "runtime_id": runtime_id,
            "ok": bool(result["ok"]),
            "latency_ms": result["latency_ms"],
            "detail": (
                "Bounded probe succeeded. No secrets were sent."
                if result["ok"]
                else "Runtime did not answer the bounded probe. Try another route."
            ),
            "secrets_sent": False,
        }

    def diagnose(self, runtime_id: str) -> dict[str, Any]:
        runtime_id = _require_runtime(runtime_id)
        hints = FIX_HINTS[runtime_id]
        spec = RUNTIME_SPECS[runtime_id]
        reduced = spec["parser"] == "generic_fallback"
        native = spec["tool_calling"] == "native"
        healthy = self._health[runtime_id] == "healthy"
        detected = self.adapter(runtime_id).configured_from_env() or healthy
        firing = reduced or (native and (detected or runtime_id == "ollama"))
        return {
            "runtime_id": runtime_id,
            "firing": bool(firing),
            "reason": hints["reason"],
            "reason_fa": hints["reason_fa"],
            "fix": hints["fix"],
            "fix_fa": hints["fix_fa"],
            "reduced_reliability": reduced,
        }

    def route(self) -> dict[str, Any]:
        active = resolve_route()
        return {
            "priority": list(ROUTE_PRIORITY),
            "active": active.name,
            "sentence_en": (
                "hosted → aval → ollama → byok → echo. The first healthy route wins. "
                f"{active.sentence_en}"
            ),
            "sentence_fa": (
                "hosted → aval → ollama → byok → echo. نخستین مسیر سالم برنده است. "
                f"{active.sentence_fa}"
            ),
        }

    def gateway_status(self) -> dict[str, Any]:
        return self.gateway.snapshot()

    def gateway_update(self, params: dict[str, Any]) -> dict[str, Any]:
        banned = ("token", "secret", "api_key", "credential", "authorization")
        for key in params:
            if str(key).lower() in banned:
                raise ProviderHubsError("gateway credentials cannot be sent over RPC")
        snapshot = self.gateway.update(
            enabled=params.get("enabled") if "enabled" in params else None,
            tool_id=params.get("tool_id") if "tool_id" in params else None,
            tool_enabled=params.get("tool_enabled") if "tool_enabled" in params else None,
            byok=params.get("byok") if "byok" in params else None,
        )
        self._persist()
        return snapshot

    def parsers(self) -> dict[str, Any]:
        return {"parsers": [dict(item) for item in PARSER_INFO]}

    def _runtime_record(self, runtime_id: str) -> dict[str, Any]:
        spec = RUNTIME_SPECS[runtime_id]
        adapter = self.adapter(runtime_id)
        detected = adapter.configured_from_env() or self._health[runtime_id] == "healthy"
        health = self._health[runtime_id]
        if health == "idle" and detected:
            health = "idle"
        tool_calling = spec["tool_calling"]
        if tool_calling == "disabled" and detected and spec["parser"] != "generic_fallback":
            tool_calling = "native"
        return {
            "id": runtime_id,
            "name": spec["name"],
            "endpoint": adapter.endpoint,
            "detected": detected,
            "health": health,
            "recommended": bool(spec["recommended"]),
            "local": True,
            "data_leaves_machine": False,
            "tool_calling": tool_calling,
            "parser": spec["parser"],
            "parser_guidance": spec["parser_guidance"],
            "models": list(self._models[runtime_id]),
            "selected_model": self._selected.get(runtime_id, ""),
            "cost_tier": spec["cost_tier"],
            "privacy_en": LOCAL_PRIVACY_EN,
            "privacy_fa": LOCAL_PRIVACY_FA,
            "fix_hint": FIX_HINTS[runtime_id]["fix"],
        }

    def _catalog_entry(self, runtime_id: str) -> dict[str, Any]:
        spec = RUNTIME_SPECS[runtime_id]
        return {
            "id": runtime_id,
            "name": spec["name"],
            "local": True,
            "runtimes": [runtime_id],
            "cost_tier": spec["cost_tier"],
            "data_leaves_machine": False,
            "privacy_en": LOCAL_PRIVACY_EN,
            "privacy_fa": LOCAL_PRIVACY_FA,
            "tool_calling": spec["parser"] != "generic_fallback",
            "notes": spec["notes"],
        }

    def _load(self) -> None:
        try:
            blob = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(blob, dict):
            return
        selected = blob.get("selected") or {}
        models = blob.get("models") or {}
        endpoints = blob.get("endpoints") or {}
        if isinstance(selected, dict):
            for runtime_id, model in selected.items():
                if runtime_id in RUNTIME_IDS and isinstance(model, str):
                    self._selected[runtime_id] = model
        if isinstance(models, dict):
            for runtime_id, rows in models.items():
                if runtime_id in RUNTIME_IDS and isinstance(rows, list):
                    self._models[runtime_id] = [str(item) for item in rows if str(item)]
        if isinstance(endpoints, dict):
            for runtime_id, endpoint in endpoints.items():
                if (
                    runtime_id in RUNTIME_IDS
                    and isinstance(endpoint, str)
                    and endpoint.startswith(("http://", "https://"))
                ):
                    self._endpoints[runtime_id] = endpoint.rstrip("/")
        gateway = blob.get("gateway")
        if isinstance(gateway, dict):
            self.gateway.load_state(gateway)

    def _persist(self) -> None:
        payload = {
            "selected": self._selected,
            "models": self._models,
            "endpoints": self._endpoints,
            "gateway": self.gateway.dump_state(),
        }
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(payload, ensure_ascii=False, indent=2)
            self.state_path.write_text(encoded, encoding="utf-8")
            os.chmod(self.state_path, 0o600)
        except OSError:
            return


def _require_runtime(runtime_id: str) -> str:
    if runtime_id not in RUNTIME_IDS:
        raise ProviderHubsError("unknown runtime")
    return runtime_id
