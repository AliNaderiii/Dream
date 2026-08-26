from __future__ import annotations

import pytest

from dream.gws.errors import GwsSecurityError
from dream.gws.http import request_json
from dream.gws.service import GoogleWorkspaceService
from dream.gws.tools import gmail_send
from dream.model_providers import KeychainCredentialStore
from tests.test_gws import MemoryKeyring


def test_network_off_blocks_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("DREAM_GOOGLE_CLIENT_ID", "dream.apps.googleusercontent.com")
    service = GoogleWorkspaceService(credentials=KeychainCredentialStore(backend=MemoryKeyring()))
    with pytest.raises(GwsSecurityError, match="DREAM_ALLOW_NETWORK"):
        service.oauth_begin()


def test_example_client_id_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")
    monkeypatch.setenv("DREAM_GOOGLE_CLIENT_ID", "EXAMPLE-not-real")
    service = GoogleWorkspaceService(credentials=KeychainCredentialStore(backend=MemoryKeyring()))
    with pytest.raises(GwsSecurityError, match="CLIENT_ID"):
        service.oauth_begin()


def test_wan_api_host_is_refused() -> None:
    with pytest.raises(GwsSecurityError, match="allow-list"):
        request_json("https://example.com/gmail")


def test_non_loopback_redirect_code_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")
    monkeypatch.setenv("DREAM_GOOGLE_CLIENT_ID", "dream.apps.googleusercontent.com")
    service = GoogleWorkspaceService(credentials=KeychainCredentialStore(backend=MemoryKeyring()))
    started = service.oauth_begin()
    with pytest.raises(GwsSecurityError, match="loopback"):
        service.oauth_complete(started["state"], "https://evil.example/callback?code=x")


def test_gmail_send_stays_human(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")
    text = gmail_send("a@b.c", "Hi", "Body")
    assert "not enabled" in text
    assert "ارسال" in text
