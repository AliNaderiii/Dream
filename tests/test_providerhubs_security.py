"""Security and no-hang checks for provider hubs."""

from __future__ import annotations

import json
import time
from pathlib import Path

from dream.model_providers import KeychainCredentialStore
from dream.providerhubs.service import ProviderHubsService
from tests.test_providerhubs import _FakeKeyring, _serve


def test_state_file_never_stores_credentials(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = KeychainCredentialStore(backend=_FakeKeyring())
    store.set("tool-gateway", "scoped-not-a-cloud-key")
    service = ProviderHubsService(state_path=path, credentials=store)
    service.gateway_update({"enabled": True, "tool_id": "tts", "tool_enabled": True})
    blob = path.read_text(encoding="utf-8")
    assert "scoped-not-a-cloud-key" not in blob
    assert "sk-" not in blob
    assert "ghp_" not in blob
    assert "AKIA" not in blob
    snapshot = service.gateway_status()
    assert snapshot["auth"] == "keychain"
    dumped = json.dumps(snapshot)
    assert "scoped-not-a-cloud-key" not in dumped


def test_probe_is_bounded(tmp_path: Path) -> None:
    service = ProviderHubsService(
        state_path=tmp_path / "down.json",
        credentials=KeychainCredentialStore(backend=_FakeKeyring()),
    )
    service._endpoints["vllm"] = "http://127.0.0.1:1/v1"
    started = time.monotonic()
    result = service.test("vllm")
    elapsed = time.monotonic() - started
    assert result["ok"] is False
    assert result["secrets_sent"] is False
    assert elapsed < 4.0


def test_live_probe_does_not_include_secrets(tmp_path: Path) -> None:
    server, endpoint = _serve()
    try:
        service = ProviderHubsService(
            state_path=tmp_path / "ok.json",
            credentials=KeychainCredentialStore(backend=_FakeKeyring()),
        )
        service._endpoints["lmstudio"] = endpoint
        result = service.test("lmstudio")
        assert result["ok"] is True
        assert result["secrets_sent"] is False
        assert "Authorization" not in json.dumps(result)
    finally:
        server.shutdown()
        server.server_close()
