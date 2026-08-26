from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dream.bridge import methods_remotegw
from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.bridge.extensions import Registry
from dream.remotegw.bind import resolve_bind
from dream.remotegw.cli import main
from dream.remotegw.errors import RemoteGwSecurityError
from dream.remotegw.service import RemoteGwService, reset_service
from dream.remotegw.tokens import RemoteTokens


@pytest.fixture()
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RemoteGwService:
    monkeypatch.setenv("DREAM_REMOTEGW_TOKENS", str(tmp_path / "tokens.json"))
    runtime = RemoteGwService(RemoteTokens(path=str(tmp_path / "tokens.json")))
    reset_service(runtime)
    yield runtime
    runtime.stop()
    reset_service(None)


def test_help_offline() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0


def test_default_bind_is_loopback() -> None:
    bind = resolve_bind(lan=False, host=None, port=None)
    assert bind["host"] == "127.0.0.1"
    assert bind["leaves_machine"] is False


def test_wan_bind_refused() -> None:
    with pytest.raises(RemoteGwSecurityError, match="WAN"):
        resolve_bind(lan=True, host="8.8.8.8", port=8765)
    with pytest.raises(RemoteGwSecurityError, match="WAN"):
        resolve_bind(lan=False, host="0.0.0.0", port=8765)


def test_lan_requires_flag() -> None:
    with pytest.raises(RemoteGwSecurityError, match="--lan"):
        resolve_bind(lan=False, host="192.168.1.10", port=8765)
    bind = resolve_bind(lan=True, host="192.168.1.10", port=8765)
    assert bind["kind"] == "lan"
    assert bind["leaves_machine"] is True


def test_read_token_cannot_issue(service: RemoteGwService) -> None:
    issued = service.issue_token(scope="read", label="Phone")
    assert issued["token"].startswith("drm_")
    assert "..." in issued["prefix"]
    info = service.tokens.verify(issued["token"], need="read")
    assert info["scope"] == "read"
    with pytest.raises(RemoteGwSecurityError, match="insufficient|read token"):
        service.tokens.verify(issued["token"], need="admin")


def test_query_string_token_rejected(service: RemoteGwService) -> None:
    started = service.start(host="127.0.0.1", port=18765)
    assert started["bind"]["host"] == "127.0.0.1"
    token = service.issue_token(scope="read")["token"]
    with pytest.raises(HTTPError) as raised:
        urlopen(f"http://127.0.0.1:18765/health?token={token}", timeout=2)
    assert raised.value.code == 400
    req = Request(
        "http://127.0.0.1:18765/rpc",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "health"}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=2) as response:
        payload = json.loads(response.read().decode())
    assert payload["result"]["status"] == "ok"


def test_bridge_handlers(service: RemoteGwService) -> None:
    status = methods_remotegw.remotegw_status({})
    assert status["auth"] == "bearer"
    assert status["query_tokens"] is False
    preview = methods_remotegw.remotegw_preview({})
    assert preview["token_in_qr"] is False
    assert preview["url"].startswith("http://127.0.0.1:")
    with pytest.raises(BridgeError) as raised:
        methods_remotegw.remotegw_preview({"host": "1.1.1.1", "lan": True})
    assert raised.value.code == INVALID_PARAMS
    assert "remotegw.status" in Registry.merged_handlers()
