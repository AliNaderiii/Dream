"""P6 L9-E — provider-hub credential and egress policy.

The fixtures here use deliberately broken shapes (``sk_EXAMPLE_...``) so
nothing in this file resembles a real credential to a scanner. What is
under test is that a *real* token — minted by the store at runtime — never
reaches a snapshot, a log line, a header dump, or an RPC reply, and that
a health probe cannot be turned into an egress channel.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from dream.providerhubs.gateway import ToolGateway
from dream.providerhubs.types import GATEWAY_TOOLS, RUNTIME_SPECS
from dream.security.providergateway import (
    GATEWAY_SCOPES,
    MAX_PROBE_BYTES,
    GatewayPolicyError,
    ScopedTokenStore,
    mint_token,
    probe_runtime,
    redact_headers,
    safe_snapshot,
    tool_enabled,
)
from dream.security.secrets import install_redaction_filter

#: Deliberately not a real shape. Never a live credential in a tracked file.
FAKE_KEY = "sk_EXAMPLE_not_a_real_key"


# --------------------------------------------------------------------------- #
# Least privilege
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("tool", GATEWAY_TOOLS)
@pytest.mark.parametrize("scope", GATEWAY_SCOPES)
def test_a_token_is_minted_for_exactly_one_tool_and_scope(tool: str, scope: str) -> None:
    secret, record = mint_token(tool, scope)
    assert record.tool == tool and record.scope == scope
    assert secret.startswith("dgw_") and len(secret) > 40


@pytest.mark.parametrize("tool", ["*", "all", "", "web_search ", "admin", "search"])
def test_a_global_or_unknown_tool_grant_is_refused(tool: str) -> None:
    with pytest.raises(GatewayPolicyError):
        mint_token(tool, "read")


@pytest.mark.parametrize("scope", ["admin", "*", "write", "", "USE"])
def test_an_out_of_model_scope_is_refused(scope: str) -> None:
    with pytest.raises(GatewayPolicyError):
        mint_token("web_search", scope)


@pytest.mark.parametrize("ttl", [0, 10, 60 * 60 * 24 * 400])
def test_an_unbounded_lifetime_is_refused(ttl: float) -> None:
    with pytest.raises(GatewayPolicyError):
        mint_token("web_search", "read", ttl_seconds=ttl)


def test_the_scope_model_has_no_wildcard() -> None:
    assert GATEWAY_SCOPES == ("read", "use")
    assert "admin" not in GATEWAY_SCOPES


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def test_a_token_verifies_only_for_its_own_tool() -> None:
    store = ScopedTokenStore()
    secret, _ = store.issue("web_search", "read")
    assert store.verify(secret, tool="web_search")[0]
    ok, refusal = store.verify(secret, tool="image")
    assert not ok and refusal is not None and refusal.code == "wrong_tool"


def test_a_read_token_cannot_be_used_to_act() -> None:
    store = ScopedTokenStore()
    secret, _ = store.issue("tts", "read")
    ok, refusal = store.verify(secret, tool="tts", scope="use")
    assert not ok and refusal is not None and refusal.code == "insufficient_scope"


def test_a_use_token_also_satisfies_read() -> None:
    store = ScopedTokenStore()
    secret, _ = store.issue("tts", "use")
    assert store.verify(secret, tool="tts", scope="read")[0]
    assert store.verify(secret, tool="tts", scope="use")[0]


def test_an_unknown_or_empty_token_is_refused() -> None:
    store = ScopedTokenStore()
    store.issue("browser", "read")
    for candidate in ("", "dgw_deadbeef", FAKE_KEY):
        ok, refusal = store.verify(candidate, tool="browser")
        assert not ok and refusal is not None


def test_an_expired_token_is_refused() -> None:
    store = ScopedTokenStore()
    secret, record = store.issue("image", "read", ttl_seconds=60)
    ok, refusal = store.verify(secret, tool="image", now=record.expires_at + 1)
    assert not ok and refusal is not None and refusal.code == "expired_token"


def test_verification_compares_every_candidate() -> None:
    # No early exit means no timing oracle for "which prefix was right".
    store = ScopedTokenStore()
    for tool in GATEWAY_TOOLS:
        store.issue(tool, "read")
    secret, _ = store.issue("web_search", "use")
    assert store.verify(secret, tool="web_search", scope="use")[0]


# --------------------------------------------------------------------------- #
# Rotation and revocation
# --------------------------------------------------------------------------- #


def test_rotation_replaces_the_secret_and_keeps_the_grant() -> None:
    store = ScopedTokenStore()
    old_secret, record = store.issue("web_search", "use", label="search")
    new_secret, rotated = store.rotate(record.token_id)
    assert new_secret != old_secret
    assert rotated.tool == "web_search" and rotated.scope == "use"
    assert rotated.rotated_from == record.token_id
    assert rotated.label == "search"
    assert not store.verify(old_secret, tool="web_search")[0]
    assert store.verify(new_secret, tool="web_search", scope="use")[0]


def test_rotating_an_unknown_token_refuses() -> None:
    with pytest.raises(GatewayPolicyError):
        ScopedTokenStore().rotate("tok_nope")


def test_revocation_is_immediate_and_idempotent() -> None:
    store = ScopedTokenStore()
    secret, record = store.issue("browser", "read")
    assert store.revoke(record.token_id) is True
    assert store.revoke(record.token_id) is False
    assert not store.verify(secret, tool="browser")[0]
    assert store.get(record.token_id) is None


# --------------------------------------------------------------------------- #
# Credentials never leave the module
# --------------------------------------------------------------------------- #


def test_a_grant_record_carries_no_secret() -> None:
    store = ScopedTokenStore()
    secret, record = store.issue("web_search", "read")
    blob = repr(record.to_dict())
    assert secret not in blob
    assert record.digest not in blob


def test_a_store_snapshot_carries_no_secret_or_digest() -> None:
    store = ScopedTokenStore()
    secret, record = store.issue("image", "use")
    blob = repr(store.snapshot())
    assert secret not in blob and record.digest not in blob
    assert "web_search" not in blob and "image" in blob


def test_safe_snapshot_drops_secret_named_fields() -> None:
    payload = {
        "token": "dgw_abc123",
        "api_key": FAKE_KEY,
        "nested": {"credential": "x", "password": "y"},
        "tool": "web_search",
        "token_id": "tok_1234",
    }
    scrubbed = safe_snapshot(payload)
    assert scrubbed["token"] == "[REDACTED:field]"
    assert scrubbed["api_key"] == "[REDACTED:field]"
    assert scrubbed["nested"]["credential"] == "[REDACTED:field]"
    assert scrubbed["tool"] == "web_search"
    assert scrubbed["token_id"] == "tok_1234"


def test_safe_snapshot_also_runs_the_value_scanner() -> None:
    shaped = "sk-" + "abcdefghij" * 3
    scrubbed = safe_snapshot({"note": f"leaked {shaped}"})
    assert shaped not in scrubbed["note"]
    assert "[REDACTED:" in scrubbed["note"]


def test_credential_headers_are_never_logged() -> None:
    store = ScopedTokenStore()
    secret, _ = store.issue("web_search", "use")
    headers = redact_headers(
        {
            "Authorization": f"Bearer {secret}",
            "X-API-Key": FAKE_KEY,
            "Cookie": "session=abc",
            "Accept": "application/json",
        }
    )
    assert secret not in repr(headers)
    assert headers["Authorization"] == "[REDACTED:header]"
    assert headers["X-API-Key"] == "[REDACTED:header]"
    assert headers["Cookie"] == "[REDACTED:header]"
    assert headers["Accept"] == "application/json"


def test_a_token_shaped_value_does_not_survive_the_log_filter(caplog: Any) -> None:
    logger = logging.getLogger("dream.test.gateway")
    install_redaction_filter("dream.test.gateway")
    shaped = "sk-" + "0123456789" * 3
    with caplog.at_level(logging.INFO, logger="dream.test.gateway"):
        logger.info("probe used %s", shaped)
    assert shaped not in caplog.text


def test_probe_results_serialise_without_credentials() -> None:
    result = probe_runtime("ollama", endpoint="http://evil.example/v1")
    payload = result.to_dict()
    assert "authorization" not in repr(payload).lower()
    assert payload["ok"] is False


# --------------------------------------------------------------------------- #
# Per-tool enablement, read through the P5 gateway
# --------------------------------------------------------------------------- #


def test_a_disabled_gateway_denies_every_tool() -> None:
    gateway = ToolGateway()
    for tool in GATEWAY_TOOLS:
        ok, refusal = tool_enabled(gateway, tool)
        assert not ok and refusal is not None and refusal.code == "gateway_disabled"


def test_enabling_one_tool_never_enables_another() -> None:
    gateway = ToolGateway()
    gateway.update(enabled=True, tool_id="web_search", tool_enabled=True)
    assert tool_enabled(gateway, "web_search")[0]
    for other in set(GATEWAY_TOOLS) - {"web_search"}:
        ok, refusal = tool_enabled(gateway, other)
        assert not ok and refusal is not None and refusal.code == "tool_disabled"


def test_an_unknown_tool_is_refused() -> None:
    ok, refusal = tool_enabled(ToolGateway(), "mine_crypto")
    assert not ok and refusal is not None and refusal.code == "unknown_tool"


def test_an_unreadable_gateway_fails_closed() -> None:
    class _Broken:
        def snapshot(self) -> dict[str, Any]:
            raise RuntimeError("state file is corrupt")

    ok, refusal = tool_enabled(_Broken(), "web_search")
    assert not ok and refusal is not None and refusal.code == "gateway_unreadable"


# --------------------------------------------------------------------------- #
# Bounded, non-exfiltrating probes
# --------------------------------------------------------------------------- #


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def _recorder(body: bytes = b'{"data": []}') -> tuple[Any, dict[str, Any]]:
    seen: dict[str, Any] = {}

    def _opener(request: Any, timeout: float | None = None) -> _Response:
        seen["url"] = request.full_url
        seen["headers"] = dict(request.headers)
        seen["timeout"] = timeout
        seen["method"] = request.get_method()
        return _Response(body)

    return _opener, seen


def test_a_probe_reaches_only_the_configured_endpoint() -> None:
    opener, seen = _recorder()
    result = probe_runtime("ollama", opener=opener)
    assert result.ok
    assert seen["url"] == str(RUNTIME_SPECS["ollama"]["endpoint"]).rstrip("/") + "/models"
    assert seen["method"] == "GET"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://169.254.169.254/latest",
        "http://evil.example/v1",
        "http://10.0.0.5:11434/v1",
        "http://127.0.0.1:9999/v1",
        "https://api.openai-like.invalid/v1",
    ],
)
def test_a_probe_refuses_an_unconfigured_endpoint(endpoint: str) -> None:
    result = probe_runtime("ollama", endpoint=endpoint)
    assert not result.ok
    assert result.refusal is not None and result.refusal.code == "endpoint_not_configured"


@pytest.mark.parametrize("endpoint", ["file:///etc/passwd", "gopher://x/v1", "ftp://x/v1"])
def test_a_probe_refuses_a_non_http_scheme(endpoint: str) -> None:
    result = probe_runtime(
        "ollama", endpoint=endpoint, allowed_endpoints={endpoint}
    )
    assert not result.ok and result.refusal is not None
    assert result.refusal.code in {"bad_scheme", "non_local_host"}


def test_a_probe_refuses_credentials_in_the_url() -> None:
    endpoint = "http://user:secret@127.0.0.1:11434/v1"
    result = probe_runtime("ollama", endpoint=endpoint, allowed_endpoints={endpoint})
    assert not result.ok and result.refusal is not None
    assert result.refusal.code == "credential_in_url"


@pytest.mark.parametrize("path", ["/../../etc/passwd", "/models\\..", "/x@evil.example"])
def test_a_probe_refuses_a_crafted_path(path: str) -> None:
    result = probe_runtime("ollama", path=path)
    assert not result.ok and result.refusal is not None and result.refusal.code == "bad_path"


def test_a_probe_refuses_an_unknown_runtime() -> None:
    result = probe_runtime("definitely-not-a-runtime")
    assert not result.ok and result.refusal is not None and result.refusal.code == "unknown_runtime"


def test_a_probe_refuses_a_non_local_host_even_when_allowlisted() -> None:
    endpoint = "http://example.com:11434/v1"
    result = probe_runtime("ollama", endpoint=endpoint, allowed_endpoints={endpoint})
    assert not result.ok and result.refusal is not None
    assert result.refusal.code == "non_local_host"


def test_a_probe_never_sends_a_credential_header() -> None:
    opener, seen = _recorder()
    probe_runtime("ollama", opener=opener)
    header_names = {str(name).lower() for name in seen["headers"]}
    assert not header_names & {"authorization", "x-api-key", "cookie", "proxy-authorization"}


def test_a_probe_always_carries_a_bounded_timeout() -> None:
    opener, seen = _recorder()
    probe_runtime("ollama", opener=opener, timeout=999)
    assert isinstance(seen["timeout"], float)
    assert 0 < seen["timeout"] <= 5.0
    probe_runtime("ollama", opener=opener, timeout=0.0001)
    assert seen["timeout"] >= 0.1


def test_a_probe_read_is_capped() -> None:
    opener, _ = _recorder(b"x" * (MAX_PROBE_BYTES * 3))
    result = probe_runtime("ollama", opener=opener)
    assert result.truncated
    assert len(result.body_preview) <= 520


def test_a_probe_preview_is_redacted() -> None:
    shaped = "sk-" + "abcdefghij" * 3
    opener, _ = _recorder(f'{{"leak": "{shaped}"}}'.encode())
    result = probe_runtime("ollama", opener=opener)
    assert shaped not in result.body_preview
    assert "[REDACTED:" in result.body_preview


def test_an_unreachable_runtime_reports_honestly_without_raising() -> None:
    def _dead(_request: Any, timeout: float | None = None) -> _Response:
        raise OSError("connection refused")

    result = probe_runtime("ollama", opener=_dead)
    assert not result.ok and result.refusal is not None and result.refusal.code == "unreachable"
    assert any("\u0600" <= ch <= "\u06ff" for ch in result.refusal.reason_fa)


def test_an_http_error_is_reported_not_raised() -> None:
    import urllib.error

    def _error(_request: Any, timeout: float | None = None) -> _Response:
        raise urllib.error.HTTPError("http://x", 503, "unavailable", {}, None)  # type: ignore[arg-type]

    result = probe_runtime("ollama", opener=_error)
    assert not result.ok and result.status == 503
    assert result.refusal is not None and result.refusal.code == "http_error"


def test_every_shipped_runtime_endpoint_is_loopback() -> None:
    # The probe's local-only rule is only meaningful if the shipped matrix
    # actually points at the loopback interface; pin that here so a future
    # cloud endpoint has to change this test deliberately.
    for spec in RUNTIME_SPECS.values():
        assert str(spec["endpoint"]).startswith(("http://127.0.0.1", "http://localhost"))


@pytest.mark.parametrize("runtime_id", sorted(RUNTIME_SPECS))
def test_every_shipped_runtime_probes_its_own_configured_endpoint(runtime_id: str) -> None:
    opener, seen = _recorder()
    result = probe_runtime(runtime_id, opener=opener)
    expected = str(RUNTIME_SPECS[runtime_id]["endpoint"]).rstrip("/")
    assert result.ok
    assert seen["url"].startswith(expected)


def test_every_refusal_is_bilingual() -> None:
    for result in (
        probe_runtime("nope"),
        probe_runtime("ollama", endpoint="http://evil.example/v1"),
        probe_runtime("ollama", path="/.."),
    ):
        assert result.refusal is not None
        assert result.refusal.reason_en
        assert any("\u0600" <= ch <= "\u06ff" for ch in result.refusal.reason_fa)
        assert "\n" in result.refusal.message()
