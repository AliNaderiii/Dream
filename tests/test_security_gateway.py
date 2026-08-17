"""Gateway token enforcement (Security audit, P-11).

The web gateway authenticates every request with a token. This suite verifies
the token manager's scope boundaries: a read token cannot mutate, a write
token can, and unknown tokens are always rejected.
"""

from __future__ import annotations

from dream.gateway_server import TokenManager, TokenScope


def _manager(tmp_path) -> TokenManager:
    return TokenManager(tokens_path=str(tmp_path / "tokens.json"))


def test_fresh_manager_has_no_tokens(tmp_path) -> None:
    assert not _manager(tmp_path).has_tokens


def test_created_token_verifies_with_its_scope(tmp_path) -> None:
    manager = _manager(tmp_path)
    token = manager.create_token(TokenScope.WRITE, "admin")
    info = manager.verify_token(token, TokenScope.WRITE)
    assert info is not None
    assert info["scope"] == "write"
    assert info["label"] == "admin"


def test_write_token_satisfies_read(tmp_path) -> None:
    manager = _manager(tmp_path)
    token = manager.create_token(TokenScope.WRITE, "admin")
    assert manager.verify_token(token, TokenScope.READ) is not None


def test_read_token_cannot_write(tmp_path) -> None:
    manager = _manager(tmp_path)
    token = manager.create_token(TokenScope.READ, "viewer")
    assert manager.verify_token(token, TokenScope.READ) is not None
    assert manager.verify_token(token, TokenScope.WRITE) is None


def test_unknown_token_is_rejected(tmp_path) -> None:
    manager = _manager(tmp_path)
    assert manager.verify_token("drm_bogus", TokenScope.READ) is None


def test_revoked_token_is_rejected(tmp_path) -> None:
    manager = _manager(tmp_path)
    token = manager.create_token(TokenScope.WRITE, "admin")
    assert manager.revoke_token(token) is True
    assert manager.verify_token(token, TokenScope.WRITE) is None


def test_listed_tokens_redact_the_secret(tmp_path) -> None:
    manager = _manager(tmp_path)
    manager.create_token(TokenScope.WRITE, "admin")
    listed = manager.list_tokens()
    assert listed
    assert "token" not in listed[0]
    assert listed[0]["prefix"].endswith("...")
