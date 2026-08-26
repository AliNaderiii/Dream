from __future__ import annotations

from pathlib import Path

import pytest

from dream.remotegw.bind import resolve_bind
from dream.remotegw.errors import RemoteGwSecurityError
from dream.remotegw.http import extract_bearer
from dream.remotegw.tokens import RemoteTokens


def test_public_and_unspecified_hosts_fail_closed() -> None:
    for host in ("1.1.1.1", "8.8.4.4", "0.0.0.0", "::", "2001:4860:4860::8888"):
        with pytest.raises(RemoteGwSecurityError):
            resolve_bind(lan=True, host=host, port=8765)


def test_query_token_extractor() -> None:
    with pytest.raises(RemoteGwSecurityError, match="query string"):
        extract_bearer({"Authorization": "Bearer drm_EXAMPLE_not_a_real_key"}, {"token": ["x"]})
    secret = extract_bearer({"Authorization": "Bearer drm_EXAMPLE_not_a_real_key"}, {})
    assert secret == "drm_EXAMPLE_not_a_real_key"


def test_fixture_token_shape_is_not_a_live_secret(tmp_path: Path) -> None:
    tokens = RemoteTokens(path=str(tmp_path / "t.json"))
    issued = tokens.issue(scope="read", label="ci")
    assert not issued["token"].startswith("sk-")
    assert not issued["token"].startswith("ghp_")
    assert "AKIA" not in issued["token"]
