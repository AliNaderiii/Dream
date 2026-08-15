"""Dynamic model-provider catalog, secure credentials, and connectivity helpers.

Provider metadata is safe to persist as JSON. Secrets are deliberately handled by
:class:`KeychainCredentialStore` and are never returned from this module, written
into the provider file, or included in an exception message.  ``keyring`` maps to
Keychain Access on macOS, Credential Manager on Windows, and Secret Service /
libsecret on Linux.

The HTTP implementation intentionally uses the standard library so the sidecar
stays small.  ``Authlib`` is an install dependency for applications that need its
higher-level OAuth integrations; Dream's desktop PKCE exchange is kept explicit
here so the state and verifier checks remain easy to audit.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge

KEYCHAIN_SERVICE = "Dream Model Providers"
PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NETWORK_TIMEOUT_SECONDS = 15.0
MODEL_CACHE_SECONDS = 15 * 60

# Public catalog only. There are no credentials in these records.
PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "website": "https://platform.openai.com",
        "docs": "https://platform.openai.com/docs/api-reference",
        "auth_type": "api_key",
        "endpoint": "https://api.openai.com/v1",
        "model_list_url": "https://api.openai.com/v1/models",
        "supports_streaming": True,
        "supports_reasoning": True,
        "default_models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o4-mini"],
    },
    "anthropic": {
        "name": "Anthropic",
        "website": "https://console.anthropic.com",
        "docs": "https://docs.anthropic.com/en/api",
        "auth_type": "api_key",
        "endpoint": "https://api.anthropic.com",
        "model_list_url": None,
        "supports_streaming": True,
        "supports_reasoning": True,
        "default_models": ["claude-sonnet-4-20250514", "claude-haiku-3-5-20241022"],
    },
    "google": {
        "name": "Google AI",
        "website": "https://aistudio.google.com",
        "docs": "https://ai.google.dev/api",
        "auth_type": "api_key",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta",
        "model_list_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "supports_streaming": True,
        "supports_reasoning": False,
        "oauth_supported": True,
        "oauth_authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "oauth_token_url": "https://oauth2.googleapis.com/token",
        "oauth_scopes": ["https://www.googleapis.com/auth/generative-language"],
        "default_models": ["gemini-2.5-pro", "gemini-2.5-flash"],
    },
    "groq": {
        "name": "Groq",
        "website": "https://console.groq.com",
        "docs": "https://console.groq.com/docs/api-reference",
        "auth_type": "api_key",
        "endpoint": "https://api.groq.com/openai/v1",
        "model_list_url": "https://api.groq.com/openai/v1/models",
        "supports_streaming": True,
        "supports_reasoning": False,
        "default_models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    },
    "together": {
        "name": "Together AI",
        "website": "https://api.together.xyz",
        "docs": "https://docs.together.ai/reference",
        "auth_type": "api_key",
        "endpoint": "https://api.together.xyz/v1",
        "model_list_url": "https://api.together.xyz/v1/models",
        "supports_streaming": True,
        "supports_reasoning": False,
        "default_models": ["meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "website": "https://openrouter.ai",
        "docs": "https://openrouter.ai/docs/api-reference/overview",
        "auth_type": "api_key",
        "endpoint": "https://openrouter.ai/api/v1",
        "model_list_url": "https://openrouter.ai/api/v1/models",
        "supports_streaming": True,
        "supports_reasoning": True,
        "default_models": [],
    },
    "ollama": {
        "name": "Ollama (Local)",
        "website": "https://ollama.com",
        "docs": "https://github.com/ollama/ollama/blob/main/docs/api.md",
        "auth_type": "none",
        "endpoint": "http://localhost:11434/v1",
        "model_list_url": "http://localhost:11434/v1/models",
        "supports_streaming": True,
        "supports_reasoning": False,
        "default_models": [],
    },
    "vllm": {
        "name": "vLLM (Custom)",
        "website": "https://docs.vllm.ai",
        "docs": "https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        "auth_type": "custom",
        "endpoint": "",
        "model_list_url": "",
        "supports_streaming": True,
        "supports_reasoning": False,
        "default_models": [],
    },
    "llamacpp": {
        "name": "llama.cpp (Local)",
        "website": "https://github.com/ggerganov/llama.cpp",
        "docs": "https://github.com/ggerganov/llama.cpp/tree/master/examples/server",
        "auth_type": "none",
        "endpoint": "http://localhost:8080/v1",
        "model_list_url": "http://localhost:8080/v1/models",
        "supports_streaming": True,
        "supports_reasoning": False,
        "default_models": [],
    },
}


class CredentialStoreUnavailable(RuntimeError):
    """Raised when the operating-system credential vault cannot be reached."""


class KeychainCredentialStore:
    """Small injectable wrapper around Python ``keyring``.

    ``backend`` may be a keyring-compatible object in tests. No fallback file is
    provided on purpose: failing closed is safer than silently persisting a key.
    """

    def __init__(self, backend: Any | None = None) -> None:
        if backend is None:
            try:
                import keyring  # type: ignore[import-not-found]
            except ImportError:
                keyring = None
            backend = keyring
        self._backend = backend

    @staticmethod
    def _account(provider_id: str, credential: str) -> str:
        _validate_provider_id(provider_id)
        if credential not in {"api_key", "oauth_access_token", "oauth_refresh_token"}:
            raise ValueError("unsupported credential kind")
        return f"provider:{provider_id}:{credential}"

    def _require_backend(self) -> Any:
        if self._backend is None:
            raise CredentialStoreUnavailable("OS keychain support is not installed")
        return self._backend

    def set(self, provider_id: str, value: str, credential: str = "api_key") -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("credential must be a non-empty string")
        try:
            self._require_backend().set_password(
                KEYCHAIN_SERVICE, self._account(provider_id, credential), value
            )
        except Exception as exc:
            raise CredentialStoreUnavailable("OS keychain rejected the credential") from exc

    def get(self, provider_id: str, credential: str = "api_key") -> str | None:
        try:
            return self._require_backend().get_password(
                KEYCHAIN_SERVICE, self._account(provider_id, credential)
            )
        except Exception as exc:
            raise CredentialStoreUnavailable("OS keychain could not read the credential") from exc

    def has(self, provider_id: str, credential: str = "api_key") -> bool:
        try:
            return bool(self.get(provider_id, credential))
        except CredentialStoreUnavailable:
            return False

    def delete(self, provider_id: str, credential: str = "api_key") -> None:
        backend = self._require_backend()
        account = self._account(provider_id, credential)
        try:
            # Avoid backend-specific "not found" exception classes.
            if backend.get_password(KEYCHAIN_SERVICE, account) is not None:
                backend.delete_password(KEYCHAIN_SERVICE, account)
        except Exception as exc:
            raise CredentialStoreUnavailable("OS keychain could not delete the credential") from exc

    def purge(self, provider_id: str) -> None:
        errors: list[Exception] = []
        for kind in ("api_key", "oauth_access_token", "oauth_refresh_token"):
            try:
                self.delete(provider_id, kind)
            except CredentialStoreUnavailable as exc:
                errors.append(exc)
        if errors:
            raise errors[0]


class ProviderRegistry:
    """CRUD, model discovery and connection tests for configured providers."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        credentials: KeychainCredentialStore | None = None,
        *,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.path = str(path)
        self.credentials = credentials or KeychainCredentialStore()
        self._opener = opener
        self._providers: dict[str, dict[str, Any]] = {}
        self.default_provider = "echo"
        self._load()

    def catalog(self) -> dict[str, dict[str, Any]]:
        """Return a JSON-safe copy of the public provider catalog."""
        return json.loads(json.dumps(PROVIDER_CATALOG))

    def list(self) -> list[dict[str, Any]]:
        return [self._public(record) for record in self._providers.values()]

    def get(self, provider_id: str) -> dict[str, Any] | None:
        record = self._providers.get(provider_id)
        return self._public(record) if record else None

    def raw(self, provider_id: str) -> dict[str, Any] | None:
        """Return a non-secret internal metadata copy for backend construction."""
        record = self._providers.get(provider_id)
        return dict(record) if record else None

    def add(
        self,
        config: Mapping[str, Any],
        *,
        provider_id: str | None = None,
        credential: str | None = None,
        set_default: bool = False,
    ) -> dict[str, Any]:
        kind = str(config.get("kind") or config.get("catalog_id") or "").lower()
        if kind not in PROVIDER_CATALOG:
            raise ValueError(f"unknown provider kind: {kind!r}")
        provider_id = provider_id or str(config.get("id") or f"{kind}-{uuid.uuid4().hex[:8]}")
        _validate_provider_id(provider_id)
        if provider_id in self._providers:
            raise ValueError(f"provider {provider_id!r} already exists")
        record = self._normalise(provider_id, kind, config)
        if credential:
            self.credentials.set(provider_id, credential)
        self._providers[provider_id] = record
        if set_default or self.default_provider == "echo":
            self.default_provider = provider_id
        self._save()
        return self._public(record)

    def update(
        self,
        provider_id: str,
        changes: Mapping[str, Any],
        *,
        credential: str | None = None,
        clear_credential: bool = False,
        set_default: bool = False,
    ) -> dict[str, Any]:
        current = self._providers.get(provider_id)
        if current is None:
            raise KeyError(provider_id)
        kind = str(changes.get("kind") or current["kind"]).lower()
        if kind not in PROVIDER_CATALOG:
            raise ValueError(f"unknown provider kind: {kind!r}")
        merged = {**current, **dict(changes)}
        record = self._normalise(provider_id, kind, merged, created_at=current["created_at"])
        if credential:
            self.credentials.set(provider_id, credential)
        elif clear_credential:
            self.credentials.delete(provider_id)
        self._providers[provider_id] = record
        if set_default:
            self.default_provider = provider_id
        self._save()
        return self._public(record)

    def delete(self, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        # Purge first. If the vault fails, retain cloud-provider metadata so the
        # user can retry instead of orphaning an undiscoverable credential.
        # Providers whose catalog auth type is "none" cannot have stored keys.
        try:
            self.credentials.purge(provider_id)
        except CredentialStoreUnavailable:
            kind = str(self._providers[provider_id]["kind"])
            if PROVIDER_CATALOG[kind]["auth_type"] != "none":
                raise
        del self._providers[provider_id]
        if self.default_provider == provider_id:
            self.default_provider = next(iter(self._providers), "echo")
        self._save()
        return True

    def credential(self, provider_id: str) -> str | None:
        """Resolve API key or OAuth access token without exposing it to callers."""
        access = self.credentials.get(provider_id, "oauth_access_token")
        return access or self.credentials.get(provider_id, "api_key")

    def models(self, provider_id: str, *, force: bool = False) -> list[str]:
        record = self._require(provider_id)
        cached_at = float(record.get("models_fetched_at") or 0)
        cached = _string_list(record.get("models"))
        if cached and not force and (time.time() - cached_at) < MODEL_CACHE_SECONDS:
            return cached

        catalog = PROVIDER_CATALOG[record["kind"]]
        model_url = str(record.get("model_list_url") or catalog.get("model_list_url") or "")
        if not model_url:
            models = _string_list(catalog.get("default_models"))
        else:
            headers = self._auth_headers(record)
            if record["kind"] == "google":
                key = self.credential(provider_id)
                if key:
                    model_url = f"{model_url}?{urlencode({'key': key})}"
            request = Request(model_url, headers=headers, method="GET")
            try:
                with self._opener(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                models = _parse_models(payload)
            except HTTPError as exc:
                raise ConnectionError(_http_failure_label(exc.code)) from None
            except (URLError, OSError, ValueError, TypeError):
                raise ConnectionError("Could not fetch the model catalog") from None
            if not models:
                models = _string_list(catalog.get("default_models"))

        record["models"] = sorted(dict.fromkeys(models), key=str.casefold)
        enabled = _string_list(record.get("enabled_models"))
        record["enabled_models"] = [m for m in enabled if m in record["models"]] or list(
            record["models"]
        )
        record["models_fetched_at"] = time.time()
        record["updated_at"] = time.time()
        self._save()
        return list(record["models"])

    def test_connection(self, provider_id: str) -> dict[str, Any]:
        record = self._require(provider_id)
        catalog = PROVIDER_CATALOG[record["kind"]]
        models = _string_list(record.get("enabled_models") or record.get("models"))
        if not models:
            models = _string_list(catalog.get("default_models"))
        if not models:
            try:
                models = self.models(provider_id)
            except ConnectionError as exc:
                return {"ok": False, "provider": provider_id, "detail": str(exc)}
        if not models:
            return {"ok": False, "provider": provider_id, "detail": "No model is available"}

        endpoint = str(record.get("endpoint") or catalog["endpoint"]).rstrip("/")
        if not endpoint:
            return {"ok": False, "provider": provider_id, "detail": "Endpoint is required"}
        model = models[0]
        headers = {"Content-Type": "application/json", **self._auth_headers(record)}
        kind = record["kind"]
        if kind == "anthropic":
            target = f"{endpoint}/v1/messages"
            payload = {
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            }
        elif kind == "google":
            key = self.credential(provider_id)
            suffix = f"?{urlencode({'key': key})}" if key else ""
            target = f"{endpoint}/models/{quote(model, safe='')}:generateContent{suffix}"
            payload = {
                "contents": [{"parts": [{"text": "ping"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            }
        else:
            target = f"{endpoint}/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "stream": False,
            }
        started = time.monotonic()
        request = Request(
            target,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._opener(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                response.read(64)
        except HTTPError as exc:
            return {"ok": False, "provider": provider_id, "detail": _http_failure_label(exc.code)}
        except (URLError, OSError, ValueError, TypeError):
            return {"ok": False, "provider": provider_id, "detail": "Connection failed"}
        latency = round((time.monotonic() - started) * 1000, 2)
        record["last_tested_at"] = time.time()
        record["last_latency_ms"] = latency
        self._save()
        return {"ok": True, "provider": provider_id, "latency_ms": latency}

    def _normalise(
        self,
        provider_id: str,
        kind: str,
        config: Mapping[str, Any],
        *,
        created_at: float | None = None,
    ) -> dict[str, Any]:
        catalog = PROVIDER_CATALOG[kind]
        endpoint = str(
            config.get("endpoint") or config.get("base_url") or catalog["endpoint"]
        ).rstrip("/")
        if kind == "vllm" and not endpoint:
            raise ValueError("an endpoint is required for vLLM")
        if endpoint and not endpoint.startswith(("http://", "https://")):
            raise ValueError("endpoint must use http or https")
        model_list_url = str(config.get("model_list_url") or catalog.get("model_list_url") or "")
        if not model_list_url and kind == "vllm" and endpoint:
            model_list_url = f"{endpoint}/models"
        custom_models = _string_list(config.get("models"))
        legacy_model = str(config.get("model") or "").strip()
        if not custom_models and legacy_model:
            custom_models = [legacy_model]
        models = custom_models or _string_list(catalog.get("default_models"))
        enabled = _string_list(config.get("enabled_models"))
        if not enabled:
            enabled = list(models)
        now = time.time()
        # Explicit allow-list: secrets and arbitrary UI fields cannot reach disk.
        return {
            "id": provider_id,
            "kind": kind,
            "name": str(config.get("name") or config.get("label") or catalog["name"]).strip(),
            "endpoint": endpoint,
            "model_list_url": model_list_url,
            "models": models,
            "enabled_models": [model for model in enabled if model in models] or list(models),
            "models_fetched_at": float(config.get("models_fetched_at") or 0),
            "oauth_client_id": str(config.get("oauth_client_id") or ""),
            "created_at": created_at or now,
            "updated_at": now,
            "last_tested_at": config.get("last_tested_at"),
            "last_latency_ms": config.get("last_latency_ms"),
        }

    def _public(self, record: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(record)
        provider_id = str(record["id"])
        result["credential_configured"] = self.credentials.has(provider_id) or self.credentials.has(
            provider_id, "oauth_access_token"
        )
        result["local"] = record["kind"] in {"ollama", "llamacpp", "vllm"}
        result["supports_reasoning"] = bool(PROVIDER_CATALOG[record["kind"]]["supports_reasoning"])
        result["supports_streaming"] = bool(PROVIDER_CATALOG[record["kind"]]["supports_streaming"])
        result["status"] = "connected" if record.get("last_tested_at") else "disconnected"
        return result

    def _auth_headers(self, record: Mapping[str, Any]) -> dict[str, str]:
        provider_id = str(record["id"])
        kind = str(record["kind"])
        if PROVIDER_CATALOG[kind]["auth_type"] == "none":
            return {}
        credential = self.credential(provider_id)
        if kind == "anthropic":
            return {
                "x-api-key": credential or "",
                "anthropic-version": "2023-06-01",
            }
        if kind == "google":
            # Google API keys use the query string; OAuth tokens use Bearer.
            access = self.credentials.get(provider_id, "oauth_access_token")
            return {"Authorization": f"Bearer {access}"} if access else {}
        if credential:
            return {"Authorization": f"Bearer {credential}"}
        return {}

    def _require(self, provider_id: str) -> dict[str, Any]:
        record = self._providers.get(provider_id)
        if record is None:
            raise KeyError(provider_id)
        return record

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                blob = json.load(handle)
        except (OSError, ValueError):
            return
        rows = blob.get("providers", {}) if isinstance(blob, dict) else {}
        self.default_provider = (
            str(blob.get("default") or "echo") if isinstance(blob, dict) else "echo"
        )
        dirty = False
        if isinstance(rows, list):
            rows = {
                str(row.get("id")): row for row in rows if isinstance(row, dict) and row.get("id")
            }
        if not isinstance(rows, dict):
            return
        for provider_id, old in rows.items():
            if not isinstance(old, dict):
                continue
            kind = str(old.get("kind") or "").lower()
            if kind not in PROVIDER_CATALOG:
                continue
            try:
                _validate_provider_id(str(provider_id))
                legacy_key = old.get("api_key")
                if isinstance(legacy_key, str) and legacy_key:
                    # One-way migration from the P-02 prototype. The key is
                    # removed from JSON even if the vault is unavailable.
                    try:
                        self.credentials.set(str(provider_id), legacy_key)
                    except CredentialStoreUnavailable:
                        pass
                    dirty = True
                self._providers[str(provider_id)] = self._normalise(
                    str(provider_id),
                    kind,
                    old,
                    created_at=float(old.get("created_at") or time.time()),
                )
            except (TypeError, ValueError):
                continue
        if dirty:
            self._save()

    def _save(self) -> None:
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"providers": self._providers, "default": self.default_provider}
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, path)


class OAuthPKCEManager:
    """Short-lived OAuth authorization state with mandatory state + PKCE checks."""

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        opener: Callable[..., Any] = urlopen,
        ttl_seconds: int = 600,
    ) -> None:
        self.registry = registry
        self._opener = opener
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, dict[str, Any]] = {}

    def begin(self, provider_id: str, redirect_uri: str) -> dict[str, str]:
        record = self.registry.raw(provider_id)
        if record is None:
            raise KeyError(provider_id)
        catalog = PROVIDER_CATALOG[record["kind"]]
        if not catalog.get("oauth_supported"):
            raise ValueError("this provider does not support OAuth")
        client_id = str(record.get("oauth_client_id") or "")
        if not client_id:
            raise ValueError("oauth_client_id is required")
        if not redirect_uri.startswith(("http://127.0.0.1", "http://localhost", "dream://")):
            raise ValueError("redirect_uri must be a loopback or Dream callback")

        state = generate_token(48)
        verifier = generate_token(96)
        challenge = create_s256_code_challenge(verifier)
        self._pending[state] = {
            "provider_id": provider_id,
            "verifier": verifier,
            "redirect_uri": redirect_uri,
            "created_at": time.monotonic(),
        }
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(catalog.get("oauth_scopes", [])),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return {"authorization_url": f"{catalog['oauth_authorize_url']}?{query}", "state": state}

    def complete(self, provider_id: str, state: str, code: str) -> dict[str, Any]:
        pending = self._pending.pop(state, None)  # one use, including failed attempts
        if pending is None or not secrets.compare_digest(str(pending["provider_id"]), provider_id):
            raise ValueError("invalid OAuth state")
        if (time.monotonic() - float(pending["created_at"])) > self.ttl_seconds:
            raise ValueError("OAuth state expired")
        if not code:
            raise ValueError("authorization code is required")
        record = self.registry.raw(provider_id)
        if record is None:
            raise KeyError(provider_id)
        catalog = PROVIDER_CATALOG[record["kind"]]
        body = urlencode(
            {
                "client_id": record["oauth_client_id"],
                "code": code,
                "code_verifier": pending["verifier"],
                "redirect_uri": pending["redirect_uri"],
                "grant_type": "authorization_code",
            }
        ).encode()
        request = Request(
            str(catalog["oauth_token_url"]),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                tokens = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ConnectionError(_http_failure_label(exc.code)) from None
        except (URLError, OSError, ValueError, TypeError):
            raise ConnectionError("OAuth token exchange failed") from None
        access = tokens.get("access_token") if isinstance(tokens, dict) else None
        if not isinstance(access, str) or not access:
            raise ConnectionError("OAuth response did not include an access token")
        self.registry.credentials.set(provider_id, access, "oauth_access_token")
        refresh = tokens.get("refresh_token")
        if isinstance(refresh, str) and refresh:
            self.registry.credentials.set(provider_id, refresh, "oauth_refresh_token")
        return {"connected": True, "provider": provider_id, "expires_in": tokens.get("expires_in")}


class AnthropicBackend:
    """Dream backend adapter for Anthropic's Messages API."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        *,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.reasoning_effort = reasoning_effort

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        system = "\n\n".join(
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        )
        conversation = [
            message for message in messages if message.get("role") in {"user", "assistant"}
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": conversation,
        }
        if system:
            payload["system"] = system
        if self.reasoning_effort:
            budget = {"low": 1024, "medium": 4096, "high": 8192}.get(self.reasoning_effort, 1024)
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
            payload["max_tokens"] = budget + 4096
        if tools:
            payload["tools"] = [
                {
                    "name": tool.get("function", {}).get("name"),
                    "description": tool.get("function", {}).get("description", ""),
                    "input_schema": tool.get("function", {}).get("parameters", {}),
                }
                for tool in tools
            ]
        request = Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # nosec B310: configured endpoint
                data = json.loads(response.read().decode())
            blocks = data.get("content", [])
            text = "".join(
                str(block.get("text") or "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
            calls = [
                {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "arguments": block.get("input") or {},
                }
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "tool_use"
            ]
            return {"content": text or None, "tool_calls": calls}
        except (HTTPError, URLError, OSError, ValueError, TypeError):
            return {
                "content": "The provider request failed. Check the provider connection.",
                "tool_calls": [],
            }


class GoogleBackend:
    """Dream backend adapter for Google's Generative Language API."""

    def __init__(self, model: str, credential: str, base_url: str, *, oauth: bool = False) -> None:
        self.model = model
        self.credential = credential
        self.base_url = base_url.rstrip("/")
        self.oauth = oauth

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        del tools  # Tool schema translation is intentionally deferred until Google supports parity.
        contents = [
            {
                "role": "model" if message.get("role") == "assistant" else "user",
                "parts": [{"text": str(message.get("content") or "")}],
            }
            for message in messages
        ]
        query = "" if self.oauth else f"?{urlencode({'key': self.credential})}"
        headers = {"Content-Type": "application/json"}
        if self.oauth:
            headers["Authorization"] = f"Bearer {self.credential}"
        request = Request(
            f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent{query}",
            data=json.dumps({"contents": contents}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # nosec B310: configured endpoint
                data = json.loads(response.read().decode())
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(str(part.get("text") or "") for part in parts)
            return {"content": text, "tool_calls": []}
        except (HTTPError, URLError, OSError, KeyError, IndexError, ValueError, TypeError):
            return {
                "content": "The provider request failed. Check the provider connection.",
                "tool_calls": [],
            }


def _validate_provider_id(provider_id: str) -> None:
    if not PROVIDER_ID_RE.fullmatch(provider_id):
        raise ValueError("provider id must contain only letters, numbers, dot, dash, or underscore")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_models(payload: Any) -> list[str]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data") or payload.get("models") or []
    else:
        rows = []
    models: list[str] = []
    for row in rows:
        if isinstance(row, str):
            model = row
        elif isinstance(row, dict):
            model = row.get("id") or row.get("name") or row.get("model")
        else:
            continue
        if isinstance(model, str) and model:
            models.append(model.removeprefix("models/"))
    return models


def _http_failure_label(status: int) -> str:
    if status in {401, 403}:
        return "Authentication failed"
    if status == 429:
        return "Provider rate limit reached"
    return f"Provider returned HTTP {status}"
