"""Sidecar provider hubs: RPC contract, adapters, diagnostics, and gateway."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from dream.bridge import methods_providerhubs
from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.providerhubs.adapters import RuntimeAdapter
from dream.providerhubs.service import ProviderHubsService
from dream.providerhubs.types import ROUTE_PRIORITY, RUNTIME_IDS


class _FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self.values[(service, account)] = password

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def delete_password(self, service: str, account: str) -> None:
        self.values.pop((service, account), None)


class _RuntimeHandler(BaseHTTPRequestHandler):
    mode = "json-tools"
    models = ["llama3.1", "qwen2.5"]
    status_override: int | None = None

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.status_override:
            self.send_response(self.status_override)
            self.end_headers()
            return
        if self.headers.get("Authorization"):
            self.server.saw_authorization = True  # type: ignore[attr-defined]
        payload = {"data": [{"id": model} for model in self.models]}
        self._write(200, payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        _body = self.rfile.read(length)
        if self.mode == "json-tools":
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"q": "tehran"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        else:
            payload = {
                "choices": [
                    {"message": {"content": ("Sure.\n{name: 'search', arguments: {q: 'tehran',}}")}}
                ]
            }
        self._write(200, payload)

    def _write(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve(mode: str = "json-tools") -> tuple[ThreadingHTTPServer, str]:
    class Handler(_RuntimeHandler):
        pass

    Handler.mode = mode
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.saw_authorization = False  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/v1"


@pytest.fixture
def service(tmp_path: Path) -> ProviderHubsService:
    from dream.model_providers import KeychainCredentialStore

    return ProviderHubsService(
        state_path=tmp_path / "state.json",
        credentials=KeychainCredentialStore(backend=_FakeKeyring()),
    )


def test_handlers_are_providerhubs_only() -> None:
    assert methods_providerhubs.HANDLERS
    assert all(name.startswith("providerhubs.") for name in methods_providerhubs.HANDLERS)
    assert set(methods_providerhubs.HANDLERS) == {
        "providerhubs.catalog",
        "providerhubs.runtimes",
        "providerhubs.health",
        "providerhubs.models",
        "providerhubs.select_model",
        "providerhubs.test",
        "providerhubs.diagnose",
        "providerhubs.route",
        "providerhubs.gateway",
        "providerhubs.gateway_update",
        "providerhubs.parsers",
    }


def test_route_priority_is_fixed(service: ProviderHubsService) -> None:
    snapshot = service.route()
    assert snapshot["priority"] == list(ROUTE_PRIORITY)
    assert snapshot["priority"] == ["hosted", "aval", "ollama", "byok", "echo"]
    assert "hosted → aval → ollama → byok → echo" in snapshot["sentence_en"]


def test_catalog_is_searchable_and_has_no_prices(service: ProviderHubsService) -> None:
    result = service.catalog("olla")
    assert result["count"] == 1
    assert result["catalog"][0]["id"] == "ollama"
    blob = json.dumps(service.catalog())
    assert "$" not in blob
    assert "rial" not in blob.lower()


def test_unknown_runtime_is_rejected(service: ProviderHubsService) -> None:
    with pytest.raises(ValueError, match="unknown runtime"):
        service.test("not-a-runtime")


def test_diagnose_fix_strings(service: ProviderHubsService) -> None:
    ollama = service.diagnose("ollama")
    assert ollama["firing"] is True
    assert "on by default" in ollama["fix"]
    vllm = service.diagnose("vllm")
    assert vllm["firing"] is False
    assert "--enable-auto-tool-choice --tool-call-parser qwen" in vllm["fix"]
    sglang = service.diagnose("sglang")
    assert "--tool-call-parser mistral" in sglang["fix"]
    llama = service.diagnose("llamacpp")
    assert "--jinja" in llama["fix"]
    studio = service.diagnose("lmstudio")
    assert "LM Studio" in studio["fix"]
    generic = service.diagnose("generic")
    assert generic["reduced_reliability"] is True
    assert generic["firing"] is True


def test_gateway_optional_and_off_by_default(service: ProviderHubsService) -> None:
    status = service.gateway_status()
    assert status["optional"] is True
    assert status["required_for_local"] is False
    assert status["enabled"] is False
    assert status["auth"] == "none"
    updated = service.gateway_update(
        {"enabled": True, "tool_id": "web_search", "tool_enabled": True}
    )
    assert updated["enabled"] is True
    search = next(tool for tool in updated["tools"] if tool["id"] == "web_search")
    assert search["enabled"] is True
    blob = json.dumps(updated)
    assert "token" not in blob.lower() or '"auth": "none"' in blob or '"auth": "keychain"' in blob
    for banned in ("sk-", "ghp_", "AKIA"):
        assert banned not in blob


def test_gateway_rejects_inline_secrets(service: ProviderHubsService) -> None:
    with pytest.raises(ValueError, match="cannot be sent"):
        service.gateway_update({"token": "not-a-secret-shape"})


def test_each_runtime_lists_models_and_chats(tmp_path: Path) -> None:
    from dream.model_providers import KeychainCredentialStore

    for runtime_id, mode in (
        ("ollama", "json-tools"),
        ("vllm", "json-tools"),
        ("sglang", "json-tools"),
        ("llamacpp", "json-tools"),
        ("lmstudio", "json-tools"),
        ("generic", "text-tools"),
    ):
        server, endpoint = _serve(mode)
        try:
            service = ProviderHubsService(
                state_path=tmp_path / f"{runtime_id}.json",
                credentials=KeychainCredentialStore(backend=_FakeKeyring()),
            )
            service._endpoints[runtime_id] = endpoint
            adapter = RuntimeAdapter(runtime_id, endpoint=endpoint)
            models = adapter.list_models()
            assert "llama3.1" in models
            health = adapter.health()
            assert health["ok"] is True
            result = adapter.chat([{"role": "user", "content": "search tehran"}])
            assert result["ok"] is True
            assert result["tool_calls"]
            assert result["tool_calls"][0]["name"] == "search"
        finally:
            server.shutdown()
            server.server_close()


def test_probe_never_sends_authorization(service: ProviderHubsService) -> None:
    server, endpoint = _serve()
    try:
        adapter = RuntimeAdapter("ollama", endpoint=endpoint)
        adapter.health()
        assert server.saw_authorization is False  # type: ignore[attr-defined]
        probe = service.test("ollama")
        assert probe["secrets_sent"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_bridge_unknown_runtime_maps_to_invalid_params(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dream.model_providers import KeychainCredentialStore

    methods_providerhubs.reset_service(
        ProviderHubsService(
            state_path=tmp_path / "rpc.json",
            credentials=KeychainCredentialStore(backend=_FakeKeyring()),
        )
    )
    with pytest.raises(BridgeError) as exc:
        methods_providerhubs.providerhubs_test({"runtime_id": "missing"})
    assert exc.value.code == INVALID_PARAMS
    methods_providerhubs.reset_service(None)


def test_runtimes_do_not_block_on_down_endpoint(service: ProviderHubsService) -> None:
    listed = service.runtimes()
    assert listed["recommended"] == "ollama"
    assert [row["id"] for row in listed["runtimes"]] == list(RUNTIME_IDS)
    allowed = {"idle", "unknown", "down", "healthy"}
    assert all(row["health"] in allowed for row in listed["runtimes"])


def test_select_model_updates_record(tmp_path: Path) -> None:
    from dream.model_providers import KeychainCredentialStore

    server, endpoint = _serve()
    try:
        service = ProviderHubsService(
            state_path=tmp_path / "select.json",
            credentials=KeychainCredentialStore(backend=_FakeKeyring()),
        )
        service._endpoints["ollama"] = endpoint
        models = service.models("ollama")
        assert "qwen2.5" in models["models"]
        record = service.select_model("ollama", "qwen2.5")
        assert record["selected_model"] == "qwen2.5"
    finally:
        server.shutdown()
        server.server_close()
