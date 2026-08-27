from __future__ import annotations

import json
from urllib.request import Request

import pytest

from dream.gws.service import GoogleWorkspaceService
from dream.model_providers import KeychainCredentialStore


class MemoryKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self.values[(service, account)] = password

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def delete_password(self, service: str, account: str) -> None:
        self.values.pop((service, account), None)


class FakeResponse:
    def __init__(self, payload: dict[str, object], url: str) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self._url = url

    def read(self, amount: int = -1) -> bytes:
        if amount < 0:
            return self._raw
        return self._raw[:amount]

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch) -> GoogleWorkspaceService:
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")
    monkeypatch.setenv("DREAM_GOOGLE_CLIENT_ID", "dream.apps.googleusercontent.com")
    store = KeychainCredentialStore(backend=MemoryKeyring())
    calls: list[str] = []

    def opener(request: Request, timeout: float) -> FakeResponse:
        del timeout
        url = request.full_url
        calls.append(url)
        if "oauth2.googleapis.com/token" in url:
            return FakeResponse(
                {"access_token": "ya29.real-token", "refresh_token": "1//refresh"},
                url,
            )
        if "gmail.googleapis.com" in url:
            return FakeResponse({"messages": [{"id": "m1"}]}, url)
        if "calendar/v3" in url:
            return FakeResponse(
                {"items": [{"summary": "Standup", "start": {"dateTime": "2026-08-26T09:00:00Z"}}]},
                url,
            )
        if "drive/v3/files" in url:
            return FakeResponse({"files": [{"name": "notes.md"}]}, url)
        raise AssertionError(url)

    service = GoogleWorkspaceService(credentials=store, opener=opener)
    service._calls = calls  # type: ignore[attr-defined]
    return service


def test_oauth_and_readonly_lists(runtime: GoogleWorkspaceService) -> None:
    started = runtime.oauth_begin()
    assert started["redirect_uri"].startswith("http://127.0.0.1:")
    assert "accounts.google.com" in started["authorization_url"]
    done = runtime.oauth_complete(started["state"], "auth-code")
    assert done["connected"] is True
    assert "m1" in runtime.gmail_list()
    assert "Standup" in runtime.calendar_list()
    assert "notes.md" in runtime.drive_list()


def test_status_names_readonly_scopes(runtime: GoogleWorkspaceService) -> None:
    shot = runtime.status()
    assert shot["writes"] is False
    assert shot["network"] is True
    assert "gmail.readonly" in shot["scopes"]
