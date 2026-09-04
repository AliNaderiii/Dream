"""SEC-11 — local-first bind, verifier token storage, and transport hardening.

This suite is intentionally stdlib-only so it runs in the project's default
CI environment (FastAPI/uvicorn are optional extras). FastAPI-level route
tests are guarded separately with ``importorskip`` and are recorded as
skipped/not executed when ``.[web]`` is not installed.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from dream.gateway_server import (
    AuthAttemptLimiter,
    GatewayConfig,
    TokenManager,
    TokenScope,
    _extract_token,
    _origin_allowed,
    _query_token_present,
    classify_gateway_host,
    gateway_origins,
    resolve_gateway_bind,
)

# --------------------------------------------------------------------------- #
# Local-first bind policy
# --------------------------------------------------------------------------- #


def test_default_bind_is_loopback() -> None:
    bind = resolve_gateway_bind(lan=False, host=None, port=None)
    assert bind["host"] == "127.0.0.1"
    assert bind["kind"] == "loopback"
    assert bind["leaves_machine"] is False


def test_lan_exposure_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="--lan"):
        resolve_gateway_bind(lan=False, host="192.168.1.10", port=9090)
    bind = resolve_gateway_bind(lan=True, host="192.168.1.10", port=9090)
    assert bind["kind"] == "lan"
    assert bind["leaves_machine"] is True


def test_public_and_unspecified_bind_is_refused() -> None:
    for host in ("0.0.0.0", "::", "8.8.4.4", "2001:4860:4860::8888"):
        with pytest.raises(ValueError):
            resolve_gateway_bind(lan=True, host=host, port=9090)


def test_lan_without_explicit_private_host_is_refused() -> None:
    with pytest.raises(ValueError, match="explicit private host"):
        resolve_gateway_bind(lan=True, host=None, port=9090)


def test_command_host_classifier_accepts_only_safe_kinds() -> None:
    assert classify_gateway_host("127.0.0.1") == "loopback"
    assert classify_gateway_host("localhost") == "loopback"
    assert classify_gateway_host("192.168.1.2") == "lan"
    with pytest.raises(ValueError):
        classify_gateway_host("0.0.0.0")


def test_out_of_range_port_is_refused() -> None:
    for port in (0, 1, 1023, 65536):
        with pytest.raises(ValueError):
            resolve_gateway_bind(lan=False, host=None, port=port)


# --------------------------------------------------------------------------- #
# Verifier-based token storage
# --------------------------------------------------------------------------- #


def test_create_token_returns_raw_once_and_persists_only_a_verifier(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    tm = TokenManager(tokens_path=str(path))
    raw = tm.create_token(scope=TokenScope.WRITE, label="Device")
    assert raw.startswith("drm_") and len(raw) > 40

    on_disk = path.read_text(encoding="utf-8")
    assert raw not in on_disk
    assert "verifier" in on_disk
    assert "id" in on_disk
    assert path.stat().st_mode & stat.S_IRWXU == 0o600


def test_list_and_all_never_leak_raw_or_verifier(tmp_path: Path) -> None:
    tm = TokenManager(tokens_path=str(tmp_path / "t.json"))
    raw = tm.create_token(scope=TokenScope.WRITE, label="Device")
    listed = tm.list_tokens()
    all_rows = tm.all_tokens()
    for row in listed:
        assert "id" in row and "prefix" in row
        assert "verifier" not in row and raw not in repr(row)
    for row in all_rows.values():
        assert "verifier" not in row and raw not in repr(row)


def test_token_scopes_and_rotation_invalidate_the_old_secret(tmp_path: Path) -> None:
    tm = TokenManager(tokens_path=str(tmp_path / "t.json"))
    old = tm.create_token(scope=TokenScope.WRITE)
    info = tm.verify_token(old, TokenScope.READ)
    assert info is not None and info["scope"] == "write"
    new = tm.rotate_token(old)
    assert new and new != old
    assert tm.verify_token(old, TokenScope.READ) is None
    assert tm.verify_token(new, TokenScope.WRITE) is not None


def test_revoke_by_raw_and_revoke_by_id(tmp_path: Path) -> None:
    tm = TokenManager(tokens_path=str(tmp_path / "t.json"))
    raw = tm.create_token(scope=TokenScope.WRITE)
    token_id = tm.list_tokens()[0]["id"]
    assert tm.revoke_token(raw) is True
    assert tm.verify_token(raw, TokenScope.READ) is None

    raw2 = tm.create_token(scope=TokenScope.READ)
    token_id2 = tm.list_tokens()[0]["id"]
    assert token_id2 != token_id
    assert tm.revoke_token(token_id2) is True
    assert tm.verify_token(raw2, TokenScope.READ) is None


def test_short_prefix_revoke_does_not_revoke(tmp_path: Path) -> None:
    tm = TokenManager(tokens_path=str(tmp_path / "t.json"))
    raw = tm.create_token()
    assert tm.revoke_token(raw[:4]) is False
    assert tm.verify_token(raw, TokenScope.READ) is not None


def test_persistence_across_reload_keeps_verifier_valid(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    raw = TokenManager(tokens_path=str(path)).create_token(scope=TokenScope.WRITE)
    reloaded = TokenManager(tokens_path=str(path))
    assert reloaded.verify_token(raw, TokenScope.WRITE) is not None


def test_malformed_store_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    path.write_text("{ broken json", encoding="utf-8")
    tm = TokenManager(tokens_path=str(path))
    assert tm.load_error is not None
    assert tm.has_tokens is False


def test_legacy_plaintext_migrates_atomically_and_removes_backup(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    raw = "drm_" + "a" * 48
    path.write_text(
        json.dumps(
            {
                raw: {
                    "scope": "write",
                    "label": "Legacy",
                    "created_at": 123.0,
                    "last_used_at": None,
                }
            }
        ),
        encoding="utf-8",
    )
    tm = TokenManager(tokens_path=str(path))
    assert tm.load_error is None
    assert tm.verify_token(raw, TokenScope.WRITE) is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 2 and raw not in str(data)
    assert not (tmp_path / "t.json.bak").exists()
    assert path.stat().st_mode & stat.S_IRWXU == 0o600


def test_legacy_malformed_row_fails_closed_and_leaves_file_untouched(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    original = json.dumps({"not-a-token": {"scope": "write"}})
    path.write_text(original, encoding="utf-8")
    tm = TokenManager(tokens_path=str(path))
    assert tm.load_error is not None
    assert tm.has_tokens is False
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "t.json.bak").exists()


def test_failed_persist_does_not_leave_partial_state(tmp_path: Path, monkeypatch) -> None:
    import dream.gateway_server as gs

    path = tmp_path / "t.json"
    # Construct through the current module attribute so a prior
    # ``importlib.reload()`` in another test cannot hand us a stale class.
    tm = gs.TokenManager(tokens_path=str(path))

    def _boom(self) -> None:  # noqa: ANN001
        raise OSError("read-only")

    monkeypatch.setattr(gs.TokenManager, "_save", _boom)
    with pytest.raises(gs.GatewayTokenStoreError):
        tm.create_token(scope=TokenScope.READ, label="x")
    assert tm.has_tokens is False


# --------------------------------------------------------------------------- #
# Bearer-only credential transport
# --------------------------------------------------------------------------- #


def _request(headers: dict[str, str], query: dict[str, list[str]]) -> SimpleNamespace:
    return SimpleNamespace(headers=headers, query_params=query)


def test_extract_token_accepts_only_authorization_bearer() -> None:
    raw = "drm_" + "b" * 48
    assert _extract_token(_request({"Authorization": f"Bearer {raw}"}, {})) == raw
    assert _extract_token(_request({"X-Access-Token": raw}, {})) is None
    assert _extract_token(_request({}, {"token": [raw]})) is None


def test_query_token_presence_is_detectable() -> None:
    assert _query_token_present(_request({}, {"token": ["x"]})) is True
    assert _query_token_present(_request({}, {})) is False


# --------------------------------------------------------------------------- #
# Origin / CORS policy
# --------------------------------------------------------------------------- #


def test_gateway_origins_include_same_origin_and_explicit_allowlist(monkeypatch) -> None:
    cfg = GatewayConfig()
    cfg.host = "127.0.0.1"
    cfg.port = 9090
    cfg.tls_enabled = False
    origins = gateway_origins(cfg)
    assert "http://127.0.0.1:9090" in origins
    assert "http://localhost:9090" in origins
    monkeypatch.setenv("DREAM_GATEWAY_ALLOWED_ORIGINS", "https://phone.example")
    cfg2 = GatewayConfig()
    cfg2.allowed_origins = ["https://phone.example"]
    assert "https://phone.example" in gateway_origins(cfg2)


def test_origin_allowed_for_same_origin_and_non_browser() -> None:
    cfg = GatewayConfig()
    cfg.host = "127.0.0.1"
    cfg.port = 9090
    assert _origin_allowed(_request({}, {}), cfg) is True
    assert (
        _origin_allowed(_request({"Origin": "http://127.0.0.1:9090"}, {}), cfg) is True
    )
    assert (
        _origin_allowed(_request({"Origin": "https://evil.example"}, {}), cfg) is False
    )


# --------------------------------------------------------------------------- #
# Bounded auth-attempt throttling
# --------------------------------------------------------------------------- #


def test_auth_attempt_limiter_enforces_budget_and_resets() -> None:
    limiter = AuthAttemptLimiter(per_minute=2)
    assert [limiter.check("10.0.0.1", now=1000 + i) for i in range(2)] == [True, True]
    assert limiter.check("10.0.0.1", now=1002) is False
    assert limiter.check("10.0.0.2", now=1002) is True
    assert limiter.check("10.0.0.1", now=1061) is True
    limiter.reset()
    assert limiter.check("10.0.0.1", now=1002) is True


# --------------------------------------------------------------------------- #
# Bridge surface: token management stays masked and id-driven
# --------------------------------------------------------------------------- #


def test_bridge_token_listing_is_masked_and_rotate_revoke_use_ids(tmp_path: Path) -> None:
    from dream.bridge.methods import BridgeMethods

    tm = TokenManager(tokens_path=str(tmp_path / "t.json"))
    raw = tm.create_token(scope=TokenScope.WRITE, label="Phone")
    bridge = BridgeMethods(token_manager=tm)

    listing = bridge.gateway_get_tokens({})
    assert raw not in repr(listing)
    row = listing["tokens"][0]
    assert row["id"] and row["prefix"].endswith("...")

    rotated = bridge.gateway_rotate_token({"token": row["id"]})
    assert rotated["token"] != raw
    assert tm.verify_token(raw, TokenScope.READ) is None
    assert tm.verify_token(rotated["token"], TokenScope.WRITE) is not None

    rotated_id = bridge.gateway_get_tokens({})["tokens"][0]["id"]
    revoked = bridge.gateway_revoke_token({"token": rotated_id})
    assert revoked["revoked"] is True
    assert tm.verify_token(rotated["token"], TokenScope.READ) is None


def test_bridge_revoke_refuses_short_prefixes(tmp_path: Path) -> None:
    from dream.bridge.errors import BridgeError
    from dream.bridge.methods import BridgeMethods

    tm = TokenManager(tokens_path=str(tmp_path / "t.json"))
    tm.create_token(scope=TokenScope.WRITE, label="Phone")
    bridge = BridgeMethods(token_manager=tm)
    with pytest.raises(BridgeError):
        bridge.gateway_revoke_token({"token": "drm_x"})


# --------------------------------------------------------------------------- #
# FastAPI app-level checks (skipped unless ``.[web]`` is installed)
# --------------------------------------------------------------------------- #


def test_fastapi_app_refuses_unsafe_bind() -> None:
    pytest.importorskip("fastapi")
    from dream.gateway_server import create_gateway_app

    cfg = GatewayConfig()
    cfg.host = "0.0.0.0"
    cfg.lan_only = True
    with pytest.raises(ValueError):
        create_gateway_app(cfg=cfg, tokens=TokenManager(tokens_path=str(Path("x"))))


def test_fastapi_app_does_not_auto_mint_setup_token() -> None:
    pytest.importorskip("fastapi")
    import tempfile

    from dream.gateway_server import create_gateway_app

    with tempfile.TemporaryDirectory() as tmp:
        tm = TokenManager(tokens_path=str(Path(tmp) / "t.json"))
        cfg = GatewayConfig()
        create_gateway_app(cfg=cfg, tokens=tm)
        assert tm.has_tokens is False
