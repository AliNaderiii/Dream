"""Provider catalog, keychain, discovery, PKCE, and redaction tests."""

from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from dream.agent import EchoBackend, OpenAIBackend
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore
from dream.model_providers import (
    KEYCHAIN_SERVICE,
    PROVIDER_CATALOG,
    KeychainCredentialStore,
    OAuthPKCEManager,
    ProviderRegistry,
)


class MemoryKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, account: str, value: str) -> None:
        self.values[(service, account)] = value

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def delete_password(self, service: str, account: str) -> None:
        self.values.pop((service, account), None)


class Response:
    def __init__(self, payload: object = None) -> None:
        self.body = json.dumps(payload if payload is not None else {"ok": True}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int | None = None) -> bytes:
        return self.body


def make_registry(tmp_path, *, opener=None):
    keyring = MemoryKeyring()
    kwargs = {"opener": opener} if opener else {}
    registry = ProviderRegistry(
        tmp_path / "providers.json", KeychainCredentialStore(keyring), **kwargs
    )
    return registry, keyring


def test_catalog_contains_every_supported_provider():
    assert set(PROVIDER_CATALOG) == {
        "openai",
        "anthropic",
        "google",
        "groq",
        "together",
        "openrouter",
        "ollama",
        "vllm",
        "llamacpp",
    }
    assert all("api_key" not in provider for provider in PROVIDER_CATALOG.values())


def test_keychain_store_retrieve_update_delete_cycle():
    backend = MemoryKeyring()
    vault = KeychainCredentialStore(backend)
    vault.set("work-openai", "secret-one")
    assert vault.get("work-openai") == "secret-one"
    vault.set("work-openai", "secret-two")
    assert vault.get("work-openai") == "secret-two"
    vault.delete("work-openai")
    assert vault.get("work-openai") is None
    assert all(service == KEYCHAIN_SERVICE for service, _account in backend.values)


def test_crud_never_persists_or_returns_api_key(tmp_path):
    registry, keyring = make_registry(tmp_path)
    created = registry.add(
        {"kind": "openai", "name": "Work", "models": ["gpt-4o-mini"]},
        provider_id="work-openai",
        credential="sk-super-secret",
    )
    assert created["credential_configured"] is True
    assert "api_key" not in created
    assert "sk-super-secret" not in (tmp_path / "providers.json").read_text()
    assert keyring.values

    updated = registry.update("work-openai", {"name": "Work 2"}, credential="sk-new")
    assert updated["name"] == "Work 2"
    assert registry.credentials.get("work-openai") == "sk-new"
    assert registry.delete("work-openai") is True
    assert keyring.values == {}
    assert registry.get("work-openai") is None


def test_legacy_inline_key_is_migrated_and_scrubbed(tmp_path):
    path = tmp_path / "providers.json"
    path.write_text(
        json.dumps(
            {
                "default": "old",
                "providers": {
                    "old": {
                        "kind": "openai",
                        "label": "Old",
                        "api_key": "legacy-secret",
                        "model": "gpt-4o-mini",
                    }
                },
            }
        )
    )
    backend = MemoryKeyring()
    registry = ProviderRegistry(path, KeychainCredentialStore(backend))
    assert registry.credentials.get("old") == "legacy-secret"
    assert "legacy-secret" not in path.read_text()
    assert "api_key" not in path.read_text()


def test_model_discovery_parses_openai_and_google_shapes(tmp_path):
    payloads = [
        Response({"data": [{"id": "gpt-b"}, {"id": "gpt-a"}]}),
        Response({"models": [{"name": "models/gemini-z"}]}),
    ]

    def opener(_request, **_kwargs):
        return payloads.pop(0)

    registry, _ = make_registry(tmp_path, opener=opener)
    registry.add({"kind": "openai"}, provider_id="openai-one", credential="secret")
    registry.add({"kind": "google"}, provider_id="google-one", credential="secret")
    assert registry.models("openai-one", force=True) == ["gpt-a", "gpt-b"]
    assert registry.models("google-one", force=True) == ["gemini-z"]


def test_test_connection_never_returns_key_or_raw_http_body(tmp_path):
    secret = "sk-never-return-this"

    def opener(request, **_kwargs):
        raise HTTPError(
            request.full_url,
            401,
            f"Authorization: Bearer {secret}",
            hdrs=None,
            fp=None,
        )

    registry, _ = make_registry(tmp_path, opener=opener)
    registry.add(
        {"kind": "openai", "models": ["gpt-4o-mini"]},
        provider_id="openai-one",
        credential=secret,
    )
    result = registry.test_connection("openai-one")
    rendered = json.dumps(result)
    assert result["detail"] == "Authentication failed"
    assert secret not in rendered
    assert "Bearer" not in rendered


def test_bridge_provider_crud_and_per_session_backend_isolation(tmp_path):
    keyring = MemoryKeyring()
    methods = BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=str(tmp_path / "sessions.json"),
        providers_path=str(tmp_path / "providers.json"),
        default_provider="echo",
        credential_store=KeychainCredentialStore(keyring),
    )
    created = methods.provider_create(
        {
            "id": "openai-one",
            "provider": {"kind": "openai", "models": ["gpt-4o-mini"]},
            "credential": "bridge-secret",
        }
    )
    assert created["provider"]["credential_configured"] is True
    assert "bridge-secret" not in json.dumps(methods.provider_list({}))

    first = methods.session_create({"provider": "echo"})["session_id"]
    second = methods.session_create({"provider": "echo"})["session_id"]
    methods.session_configure(
        {
            "session_id": first,
            "provider": "openai-one",
            "model": "gpt-4o-mini",
            "reasoning_effort": 1,
        }
    )
    assert isinstance(methods.sessions[first].dream.backend, OpenAIBackend)
    assert methods.sessions[first].dream.backend.reasoning_effort == "high"
    assert isinstance(methods.sessions[second].dream.backend, EchoBackend)
    assert methods.sessions[second].provider == "echo"

    methods.provider_delete({"id": "openai-one"})
    assert keyring.values == {}


def test_pkce_has_state_s256_and_rejects_replay(tmp_path):
    registry, _ = make_registry(tmp_path)
    registry.add(
        {"kind": "google", "oauth_client_id": "desktop-client"},
        provider_id="google-one",
        credential="temporary-api-key",
    )
    manager = OAuthPKCEManager(registry)
    started = manager.begin("google-one", "http://127.0.0.1:49152/callback")
    query = parse_qs(urlparse(started["authorization_url"]).query)
    assert query["state"] == [started["state"]]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) >= 43

    with pytest.raises(ValueError, match="invalid OAuth state"):
        manager.complete("google-one", "wrong-state", "code")


def test_pkce_exchange_stores_tokens_only_in_keychain(tmp_path):
    captured_body = b""

    def opener(request, **_kwargs):
        nonlocal captured_body
        captured_body = request.data
        return Response(
            {"access_token": "oauth-access", "refresh_token": "oauth-refresh", "expires_in": 3600}
        )

    registry, _ = make_registry(tmp_path)
    registry.add(
        {"kind": "google", "oauth_client_id": "desktop-client"},
        provider_id="google-one",
        credential="temporary-api-key",
    )
    manager = OAuthPKCEManager(registry, opener=opener)
    started = manager.begin("google-one", "http://localhost:8765/callback")
    completed = manager.complete("google-one", started["state"], "authorization-code")
    assert completed["connected"] is True
    assert b"code_verifier=" in captured_body
    assert registry.credentials.get("google-one", "oauth_access_token") == "oauth-access"
    persisted = (tmp_path / "providers.json").read_text()
    assert "oauth-access" not in persisted
    assert "oauth-refresh" not in persisted
