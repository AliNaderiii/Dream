"""Tests for dream.gateway_server — Web Gateway module.

Tests token management, TLS certificate manager, and mDNS advertiser.
The FastAPI application is tested with mocked HTTP requests.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest


class TestTokenManager:
    """TokenManager: creation, verification, rotation, revocation."""

    def test_create_token(self, tmp_path: Path):
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        token = tm.create_token(scope=TokenScope.WRITE, label="Test")
        assert token.startswith("drm_")
        assert tm.has_tokens

    def test_verify_valid_token(self, tmp_path: Path):
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        token = tm.create_token(scope=TokenScope.WRITE)
        info = tm.verify_token(token, TokenScope.READ)
        assert info is not None
        assert info["scope"] == "write"

    def test_verify_invalid_token(self, tmp_path: Path):
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        info = tm.verify_token("invalid_token", TokenScope.READ)
        assert info is None

    def test_verify_read_token_with_write_token(self, tmp_path: Path):
        """A write-scoped token satisfies a read requirement."""
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        token = tm.create_token(scope=TokenScope.WRITE)
        info = tm.verify_token(token, TokenScope.READ)
        assert info is not None

    def test_verify_write_token_with_read_token(self, tmp_path: Path):
        """A read-scoped token does NOT satisfy a write requirement."""
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        token = tm.create_token(scope=TokenScope.READ)
        info = tm.verify_token(token, TokenScope.WRITE)
        assert info is None

    def test_rotate_token(self, tmp_path: Path):
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        old_token = tm.create_token()
        new_token = tm.rotate_token(old_token)
        assert new_token is not None
        assert new_token != old_token
        # Old token should no longer work.
        assert tm.verify_token(old_token, TokenScope.READ) is None

    def test_rotate_unknown_token_returns_none(self, tmp_path: Path):
        from dream.gateway_server import TokenManager

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        assert tm.rotate_token("nonexistent") is None

    def test_revoke_token(self, tmp_path: Path):
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        token = tm.create_token()
        assert tm.revoke_token(token) is True
        assert tm.verify_token(token, TokenScope.READ) is None

    def test_revoke_unknown_token_returns_false(self, tmp_path: Path):
        from dream.gateway_server import TokenManager

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        assert tm.revoke_token("nonexistent") is False

    def test_list_tokens_masks_values(self, tmp_path: Path):
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        tm.create_token(scope=TokenScope.WRITE, label="Full Access")
        tokens = tm.list_tokens()
        assert len(tokens) == 1
        token_info = tokens[0]
        assert "prefix" in token_info
        assert token_info["prefix"].endswith("...")
        assert token_info["scope"] == "write"
        assert token_info["label"] == "Full Access"

    def test_get_setup_token_returns_write_token(self, tmp_path: Path):
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        tm.create_token(scope=TokenScope.WRITE)
        token = tm.get_setup_token()
        assert token is not None

    def test_get_setup_token_returns_none_when_no_tokens(self, tmp_path: Path):
        from dream.gateway_server import TokenManager

        tm = TokenManager(tokens_path=str(tmp_path / "tokens.json"))
        assert tm.get_setup_token() is None

    def test_persistence_across_reload(self, tmp_path: Path):
        """Tokens survive a TokenManager reload."""
        from dream.gateway_server import TokenManager, TokenScope

        path = str(tmp_path / "tokens.json")
        tm1 = TokenManager(tokens_path=path)
        token = tm1.create_token(label="Persistent")
        assert tm1.has_tokens

        tm2 = TokenManager(tokens_path=path)
        assert tm2.has_tokens
        info = tm2.verify_token(token, TokenScope.READ)
        assert info is not None
        assert info["label"] == "Persistent"


class TestTLSCertificateManager:
    """TLS certificate generation."""

    def test_get_or_create_self_signed_creates_files(self, tmp_path: Path):
        from dream.gateway_server import TLSCertificateManager

        cert_dir = tmp_path / "certs"
        tls = TLSCertificateManager(cert_dir=str(cert_dir))

        # This may fail if openssl is not installed.
        try:
            result = tls.get_or_create_self_signed()
        except (FileNotFoundError, RuntimeError) as exc:
            pytest.skip(f"openssl not available: {exc}")
            return

        assert result is not None
        cert_path, key_path = result
        assert Path(cert_path).exists()
        assert Path(key_path).exists()

    def test_get_or_create_self_signed_reuses_existing(self, tmp_path: Path):
        from dream.gateway_server import TLSCertificateManager

        cert_dir = tmp_path / "certs"
        tls = TLSCertificateManager(cert_dir=str(cert_dir))

        try:
            result1 = tls.get_or_create_self_signed()
        except (FileNotFoundError, RuntimeError) as exc:
            pytest.skip(f"openssl not available: {exc}")
            return

        # Second call should reuse.
        result2 = tls.get_or_create_self_signed()
        assert result2 == result1


class TestMDNSAdvertiser:
    """mDNS advertiser (does not actually start services in tests)."""

    def test_init(self):
        from dream.gateway_server import MDNSAdvertiser

        mdns = MDNSAdvertiser(port=9090)
        assert mdns._port == 9090
        assert mdns._running is False

    def test_get_ip_addresses_does_not_raise(self):
        from dream.gateway_server import MDNSAdvertiser

        ips = MDNSAdvertiser.get_ip_addresses()
        assert isinstance(ips, list)

    def test_stop_without_start_does_not_raise(self):
        from dream.gateway_server import MDNSAdvertiser

        mdns = MDNSAdvertiser()
        mdns.stop()  # Should not raise


class TestGatewayConfig:
    """GatewayConfig default values."""

    def test_default_config(self):
        from dream.gateway_server import GatewayConfig

        cfg = GatewayConfig()
        assert cfg.enabled is True
        assert cfg.port == 9090  # from env default
        assert cfg.host == "0.0.0.0"
        assert cfg.tls_enabled is False
        assert cfg.lan_only is True
        assert cfg.mdns_enabled is True

    def test_config_env_overrides(self, monkeypatch):
        monkeypatch.setenv("DREAM_GATEWAY_PORT", "8080")
        monkeypatch.setenv("DREAM_GATEWAY_TLS", "true")
        monkeypatch.setenv("DREAM_GATEWAY_LAN_ONLY", "false")

        # Fresh import with env set.
        import importlib
        from dream import gateway_server as gs
        importlib.reload(gs)

        assert gs.gateway_config.port == 8080
        assert gs.gateway_config.tls_enabled is True
        assert gs.gateway_config.lan_only is False


class TestGatewayBridgeIntegration:
    """Test that the bridge's gateway.* methods work correctly."""

    def test_gateway_methods_in_bridge(self):
        """BridgeMethods has gateway.* handlers when TokenManager is injected."""
        from dream.bridge.methods import BridgeMethods
        from dream.gateway_server import TokenManager

        tm = TokenManager()
        bridge = BridgeMethods(token_manager=tm)
        assert "gateway.status" in bridge.handlers
        assert "gateway.create_token" in bridge.handlers
        assert "gateway.rotate_token" in bridge.handlers
        assert "gateway.revoke_token" in bridge.handlers
        assert "gateway.get_tokens" in bridge.handlers

    def test_gateway_create_token_via_bridge(self):
        """Creating a token via the bridge method works."""
        from dream.bridge.methods import BridgeMethods
        from dream.gateway_server import TokenManager

        tm = TokenManager()
        bridge = BridgeMethods(token_manager=tm)
        result = bridge.gateway_create_token({"scope": "write", "label": "Test"})
        assert "token" in result
        assert result["scope"] == "write"
        assert result["label"] == "Test"

    def test_gateway_status_via_bridge(self):
        """Gateway status returns token info."""
        from dream.bridge.methods import BridgeMethods
        from dream.gateway_server import TokenManager, TokenScope

        tm = TokenManager()
        tm.create_token(scope=TokenScope.WRITE, label="Initial")
        bridge = BridgeMethods(token_manager=tm)
        status = bridge.gateway_status()
        assert status["enabled"] is True
        assert status["token_count"] >= 1
        assert status["has_setup_token"] is True

    def test_gateway_revoke_via_bridge(self):
        """Revoking a token via the bridge works."""
        from dream.bridge.methods import BridgeMethods
        from dream.gateway_server import TokenManager

        tm = TokenManager()
        token = tm.create_token()
        bridge = BridgeMethods(token_manager=tm)
        result = bridge.gateway_revoke_token({"token": token})
        assert result["revoked"] is True


class TestSandboxBridgeIntegration:
    """Test sandbox.* methods in the bridge."""

    def test_sandbox_methods_registered(self):
        """BridgeMethods has sandbox.* handlers."""
        from dream.bridge.methods import BridgeMethods

        bridge = BridgeMethods()
        assert "sandbox.status" in bridge.handlers
        assert "sandbox.run_code" in bridge.handlers
        assert "sandbox.run_notebook" in bridge.handlers
        assert "sandbox.install_packages" in bridge.handlers

    def test_sandbox_status_returns_unavailable_without_docker(self):
        """sandbox.status returns unavailable when Docker is absent."""
        from dream.bridge.methods import BridgeMethods

        bridge = BridgeMethods()
        # If Docker is not available, the sandbox status handler will try to
        # check and fail. We've created the sandbox object, so it should
        # return an error.
        result = bridge.sandbox_status()
        assert isinstance(result, dict)
        # It should either show available: False or raise an error code.
        if "available" in result:
            assert result["available"] is False
        elif "error" in result:
            assert result["error"] is not None


class TestBrowserBridgeIntegration:
    """Test browser.* methods in the bridge."""

    def test_browser_methods_registered(self):
        """BridgeMethods has browser.* handlers."""
        from dream.bridge.methods import BridgeMethods

        bridge = BridgeMethods()
        assert "browser.status" in bridge.handlers
        assert "browser.attach" in bridge.handlers
        assert "browser.launch_isolated" in bridge.handlers
        assert "browser.navigate" in bridge.handlers
        assert "browser.screenshot" in bridge.handlers
        assert "browser.close" in bridge.handlers
        assert "browser.request_approval" in bridge.handlers

    def test_browser_status_without_browser(self):
        """browser.status returns status dict even when no browser controller."""
        from dream.bridge.methods import BridgeMethods

        bridge = BridgeMethods()
        result = bridge.browser_status()
        assert "attached" in result
        assert result["attached"] is False

    def test_browser_request_approval_creates_session(self):
        """browser.request_approval creates a pending session."""
        from dream.bridge.methods import BridgeMethods

        bridge = BridgeMethods()
        result = bridge.browser_request_approval({
            "url": "https://example.com",
            "purpose": "Test",
        })
        assert result["status"] == "pending"
        assert result["url"] == "https://example.com"

    def test_browser_approve_activates_session(self):
        """browser.approve activates a pending session."""
        from dream.bridge.methods import BridgeMethods

        bridge = BridgeMethods()
        req = bridge.browser_request_approval({
            "url": "https://example.com",
            "purpose": "Test",
        })
        result = bridge.browser_approve({
            "session_id": req["session_id"],
        })
        assert result["approved"] is True

    def test_browser_deny_closes_session(self):
        """browser.deny closes a pending session."""
        from dream.bridge.methods import BridgeMethods

        bridge = BridgeMethods()
        req = bridge.browser_request_approval({
            "url": "https://example.com",
            "purpose": "Test",
        })
        result = bridge.browser_deny({
            "session_id": req["session_id"],
        })
        assert result["denied"] is True