"""Stage E — L1 per-linked-user scopes (G-01), approval throttling (G-02),
constant-time gateway tokens (G-03).

Scope model, policy ceiling, floor-precedence under scopes, per-user
approval-attempt budgets, gateway end-to-end enforcement with a real
Gateway + scripted tool calls, the bridge management surface, and the
constant-time verification behaviour.
"""

from __future__ import annotations

import tempfile
from types import SimpleNamespace

import pytest

from dream.agent import ApprovalPolicy, Dream
from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.connectivity.auth import DEFAULT_SCOPE, USER_SCOPES, AuthStore, validate_scope
from dream.connectivity.ratelimit import ApprovalAttemptLimiter
from dream.gateway_server import TokenManager, TokenScope
from dream.memory import MemoryStore

# -- the scope model ----------------------------------------------------------- #


def test_scopes_are_a_fixed_ordered_set() -> None:
    assert USER_SCOPES == ("chat_only", "safe_tools", "guarded_tools", "admin")
    assert DEFAULT_SCOPE == "admin"
    with pytest.raises(ValueError, match="scope must be one of"):
        validate_scope("root")


def test_link_defaults_to_admin_and_persists_scope(tmp_path) -> None:
    store = AuthStore(str(tmp_path / "links.json"))
    user = store.link("telegram", "u1")
    assert user.scope == "admin"
    reloaded = AuthStore(str(tmp_path / "links.json"))
    assert reloaded.scope_of("telegram", "u1") == "admin"


def test_set_scope_validates_and_refuses_unknown_users(tmp_path) -> None:
    store = AuthStore(str(tmp_path / "links.json"))
    store.link("telegram", "u1")
    with pytest.raises(ValueError):
        store.set_scope("telegram", "u1", "superuser")
    with pytest.raises(KeyError):
        store.set_scope("telegram", "stranger", "chat_only")
    user = store.set_scope("telegram", "u1", "safe_tools")
    assert user.scope == "safe_tools"
    assert AuthStore(str(tmp_path / "links.json")).scope_of("telegram", "u1") == "safe_tools"


def test_unknown_scope_in_stored_json_falls_back_to_admin(tmp_path) -> None:
    path = tmp_path / "links.json"
    path.write_text(
        '{"telegram": {"u1": {"display_name": "x", "linked_at": 1.0, "scope": "bogus"}}}',
        encoding="utf-8",
    )
    assert AuthStore(str(path)).scope_of("telegram", "u1") == "admin"


def test_scope_of_unknown_identity_keeps_the_legacy_default(tmp_path) -> None:
    # Scopes govern linked identities; open platforms keep pre-scope
    # behaviour (documented residual risk, threat model §7).
    assert AuthStore(str(tmp_path / "links.json")).scope_of("telegram", "ghost") == DEFAULT_SCOPE


# -- the policy ceiling ---------------------------------------------------------- #


def _policy(scope: str) -> ApprovalPolicy:
    return ApprovalPolicy(scope=scope)


@pytest.mark.parametrize(
    ("scope", "tool", "allowed"),
    [
        ("chat_only", "calculate", False),
        ("chat_only", "write_note", False),
        ("chat_only", "run_shell", False),
        ("safe_tools", "calculate", True),
        ("safe_tools", "write_note", False),
        ("safe_tools", "run_shell", False),
        ("guarded_tools", "calculate", True),
        ("guarded_tools", "write_note", True),
        ("guarded_tools", "run_shell", False),
        ("admin", "calculate", True),
        ("admin", "write_note", True),
    ],
)
def test_scope_ceiling_matrix(scope: str, tool: str, allowed: bool) -> None:
    ok, reason = _policy(scope).allows(tool, {})
    assert ok is allowed, reason
    if not allowed:
        assert "scope" in reason


def test_admin_dangerous_still_goes_through_the_approval_engine() -> None:
    ok, reason = _policy("admin").allows("run_shell", {"command": "echo scoped"})
    assert not ok and "no approver" in reason  # unchanged pre-scope behaviour


def test_floor_precedes_the_scope_gate() -> None:
    ok, reason = _policy("admin").allows("run_shell", {"command": "rm -rf /"})
    assert not ok
    assert "security floor" in reason  # not "scope … does not allow it"


def test_scope_denial_names_the_scope() -> None:
    ok, reason = _policy("safe_tools").allows("run_shell", {"command": "echo x"})
    assert not ok
    assert "'safe_tools'" in reason


# -- approval-attempt throttling (G-02) ------------------------------------------- #


def test_approval_limiter_enforces_the_budget_per_user() -> None:
    limiter = ApprovalAttemptLimiter(per_minute=3)
    assert [limiter.allow("telegram", "u1", now=100 + i) for i in range(3)] == [True] * 3
    assert limiter.allow("telegram", "u1", now=103) is False
    assert limiter.allow("telegram", "u2", now=103) is True  # budgets are per user
    assert limiter.allow("telegram", "u1", now=161) is True  # next window


def test_policy_refuses_when_the_budget_is_spent() -> None:
    limiter = ApprovalAttemptLimiter(per_minute=2)
    policy = ApprovalPolicy(scope="admin", attempt_limiter=limiter.limiter_for("tg", "u1"))
    for _ in range(2):
        ok, reason = policy.allows("run_shell", {"command": "echo hi"})
        assert not ok and "no approver" in reason  # attempts reach the engine
    ok, reason = policy.allows("run_shell", {"command": "echo hi"})
    assert not ok
    assert "too many approval attempts" in reason


def test_floor_blocked_attempts_do_not_spend_budget() -> None:
    limiter = ApprovalAttemptLimiter(per_minute=1)
    policy = ApprovalPolicy(scope="admin", attempt_limiter=limiter.limiter_for("tg", "u1"))
    ok, reason = policy.allows("run_shell", {"command": "rm -rf /"})
    assert not ok and "security floor" in reason
    assert limiter.allow("tg", "u1") is True  # the budget is untouched


def test_scope_blocked_attempts_do_not_spend_budget() -> None:
    limiter = ApprovalAttemptLimiter(per_minute=1)
    policy = ApprovalPolicy(scope="chat_only", attempt_limiter=limiter.limiter_for("tg", "u1"))
    ok, reason = policy.allows("run_shell", {"command": "echo hi"})
    assert not ok and "scope" in reason
    assert limiter.allow("tg", "u1") is True


# -- gateway end-to-end enforcement ------------------------------------------------- #


class _ScriptedBackend:
    """One scripted tool call, then prose; records tool results it receives."""

    def __init__(self, name: str, arguments: dict) -> None:
        self.call = (name, arguments)
        self.tool_results: list[str] = []

    def chat(self, messages, tools=None):
        if messages[-1]["role"] == "tool":
            self.tool_results.append(str(messages[-1]["content"]))
            return {"content": "done", "tool_calls": []}
        name, arguments = self.call
        return {
            "content": None,
            "tool_calls": [{"id": "s1", "name": name, "arguments": arguments}],
        }


class _ToolDreamFactory:
    def __init__(self, backend: _ScriptedBackend) -> None:
        self.backend = backend

    def __call__(self):
        return Dream(MemoryStore(":memory:"), self.backend, ApprovalPolicy())


def _fake_gateway(tmp_path, backend: _ScriptedBackend):
    from dream.connectivity.config import ConnectivityConfig
    from dream.connectivity.gateway import Gateway

    config = ConnectivityConfig(str(tmp_path / "config.json"))
    config.set("fake", {"enabled": True})
    gateway = Gateway(
        config,
        sessions_path=str(tmp_path / "sessions.json"),
        links_path=str(tmp_path / "links.json"),
        log_path=str(tmp_path / "log.jsonl"),
        dream_factory=_ToolDreamFactory(backend),
    )
    return gateway


def test_gateway_applies_the_live_scope_to_turns(tmp_path, monkeypatch) -> None:
    import dream.tools as tools

    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    backend = _ScriptedBackend("write_note", {"filename": "x.txt", "content": "y"})
    gateway = _fake_gateway(tmp_path, backend)
    gateway._auth.link("fake", "u1")

    import asyncio

    adapter = SimpleNamespace(
        send_typing_indicator=lambda user_id: asyncio.sleep(0),
    )
    # admin: guarded tool reaches the engine (auto-approved tier) and runs
    asyncio.run(gateway._agent_reply(adapter, "fake", "u1", "write it"))
    assert backend.tool_results and "blocked" not in backend.tool_results[0]

    # drop the user to safe_tools: the same guarded call is now refused
    gateway.set_user_scope("fake", "u1", "safe_tools")
    backend.tool_results.clear()
    asyncio.run(gateway._agent_reply(adapter, "fake", "u1", "write it"))
    assert backend.tool_results
    assert "scope 'safe_tools' does not allow it" in backend.tool_results[0]

    # chat_only: even safe tools are refused
    gateway.set_user_scope("fake", "u1", "chat_only")
    backend.call = ("calculate", {"expression": "1+1"})
    backend.tool_results.clear()
    asyncio.run(gateway._agent_reply(adapter, "fake", "u1", "calc"))
    assert backend.tool_results
    assert "scope 'chat_only' does not allow it" in backend.tool_results[0]


def test_gateway_throttles_repeated_dangerous_attempts(tmp_path) -> None:
    backend = _ScriptedBackend("run_shell", {"command": "echo hi"})
    gateway = _fake_gateway(tmp_path, backend)
    gateway._auth.link("fake", "u1")
    gateway._approval_throttle = ApprovalAttemptLimiter(per_minute=2)

    import asyncio

    adapter = SimpleNamespace(send_typing_indicator=lambda user_id: asyncio.sleep(0))
    for _ in range(3):
        backend.tool_results.clear()
        asyncio.run(gateway._agent_reply(adapter, "fake", "u1", "run"))
        assert backend.tool_results
    assert "too many approval attempts" in backend.tool_results[0]


# -- the bridge management surface ---------------------------------------------------- #


def _make_methods(tmp_path, monkeypatch) -> BridgeMethods:
    monkeypatch.setenv("DREAM_CONNECTIVITY_PATH", str(tmp_path / "connectivity.json"))
    return BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
    )


def test_bridge_set_user_scope_validates_at_the_boundary(tmp_path, monkeypatch) -> None:
    methods = _make_methods(tmp_path, monkeypatch)
    gateway = methods._ensure_gateway()
    gateway._auth.link("telegram", "u1")

    with pytest.raises(BridgeError):
        methods.gateway_set_user_scope({"platform": "telegram", "user_id": "u1", "scope": "root"})
    with pytest.raises(BridgeError):
        methods.gateway_set_user_scope({"platform": "", "user_id": "u1", "scope": "admin"})
    with pytest.raises(BridgeError):
        methods.gateway_set_user_scope({"platform": "telegram", "user_id": 42, "scope": "admin"})
    with pytest.raises(BridgeError):
        methods.gateway_set_user_scope(
            {"platform": "telegram", "user_id": "ghost", "scope": "admin"}
        )

    out = methods.gateway_set_user_scope(
        {"platform": "telegram", "user_id": "u1", "scope": "guarded_tools"}
    )
    assert out == {
        "updated": True,
        "platform": "telegram",
        "user_id": "u1",
        "scope": "guarded_tools",
    }
    assert gateway._auth.scope_of("telegram", "u1") == "guarded_tools"


def test_bridge_linked_users_rows_carry_the_scope(tmp_path, monkeypatch) -> None:
    methods = _make_methods(tmp_path, monkeypatch)
    gateway = methods._ensure_gateway()
    gateway._auth.link("telegram", "u1")
    gateway._auth.link("telegram", "u2", scope="safe_tools")
    rows = methods.gateway_linked_users({"platform": "telegram"})["linked_users"]
    by_user = {row["user_id"]: row for row in rows}
    assert by_user["u1"]["scope"] == "admin"
    assert by_user["u2"]["scope"] == "safe_tools"


# -- constant-time token verification (G-03) ---------------------------------------------- #


def test_constant_time_verification_keeps_every_semantic(tmp_path) -> None:
    manager = TokenManager(str(tmp_path / "tokens.json"))
    read = manager.create_token(TokenScope.READ, "phone")
    write = manager.create_token(TokenScope.WRITE, "desktop")

    assert manager.verify_token(read, TokenScope.READ) is not None
    assert manager.verify_token(read, TokenScope.WRITE) is None
    assert manager.verify_token(write, TokenScope.READ) is not None
    # a near-miss sharing a long prefix must not verify
    assert manager.verify_token(read[:-1] + ("a" if read[-1] != "a" else "b")) is None
    assert manager.verify_token("drm_" + "0" * 60) is None

    rotated = manager.rotate_token(read)
    assert rotated and manager.verify_token(read) is None
    assert manager.verify_token(rotated, TokenScope.READ) is not None
