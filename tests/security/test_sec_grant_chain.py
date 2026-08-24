"""Stage E — L7 isolation (G-18, G-19, G-20).

Mechanical assertions over the subagent and council grant chains (minimal
grants, no verbatim parent closures, approver-less child policies), the
degraded grant set for autonomous dreams, and fail-closed session access
across the bridge surface.
"""

from __future__ import annotations

import asyncio
import inspect
import random
import tempfile

import pytest

from dream.agent import INSTANCE_BOUND_TOOL_NAMES
from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore
from dream.subagents import DEFAULT_TOOL_GRANT, build_child_tools
from dream.tools import REGISTRY

SEED = 20260825


# -- G-19: the grant chain is mechanically minimal ------------------------------ #


def test_default_grant_never_contains_dangerous_tools() -> None:
    # Instance-bound names (remember_fact, …) are absent from the global
    # registry by design; the invariant is about risk tiers of real tools.
    for name in DEFAULT_TOOL_GRANT:
        if name in REGISTRY:
            assert REGISTRY[name].risk != "dangerous", name
    assert "run_shell" not in DEFAULT_TOOL_GRANT
    assert "send_email" not in DEFAULT_TOOL_GRANT


def test_seeded_grant_sweep_holds_every_invariant() -> None:
    rng = random.Random(SEED)
    names = sorted(REGISTRY)
    dangerous = [n for n in names if REGISTRY[n].risk == "dangerous"]
    bound = [n for n in names if n in INSTANCE_BOUND_TOOL_NAMES]
    for trial in range(60):
        sample = rng.sample(names, rng.randrange(1, len(names) + 1))
        if trial % 5 == 0:  # make sure hot names always appear
            sample = list({*sample, *dangerous, *bound})
        allow = rng.random() < 0.3
        before = dict(REGISTRY)
        child, table = build_child_tools(
            MemoryStore(":memory:"), sample, allow_dangerous=allow
        )
        try:
            # 1. no dangerous tool without the explicit flag
            if not allow:
                assert all(t.risk != "dangerous" for t in table.values())
            # 2. every granted tool is risk-resolved from the private table
            assert child.approval_policy.registry is table
            # 3. no approver ever rides along to a child
            assert child.approval_policy.ask is None
            # 4. instance-bound parent closures never pass through verbatim
            for name, tool in table.items():
                if name in INSTANCE_BOUND_TOOL_NAMES and name in before:
                    assert tool is not before[name], name
            # 5. a granted dangerous tool is STILL refused at call time
            if allow:
                for name, tool in table.items():
                    if tool.risk == "dangerous":
                        ok, reason = child.approval_policy.allows(name, {})
                        assert not ok
                        assert "no approver" in reason
            # 6. unknown grants read as unknown tools, never global fallback
            ok, reason = child.approval_policy.allows("definitely_not_granted", {})
            assert not ok and reason == "unknown tool"
        finally:
            # 7. the global registry survives byte-identically
            assert REGISTRY == before


def test_council_stages_are_built_without_dangerous() -> None:
    from dream.council import COUNCIL_ROLES, _stage_spec

    for role in COUNCIL_ROLES:
        spec = _stage_spec(role, "topic", None, "echo")
        assert spec.allow_dangerous is False, role
        assert spec.tools is None  # default grant, which carries no dangerous


def test_council_member_tables_carry_no_dangerous_tools() -> None:
    from dream.council import COUNCIL_ROLES, _stage_spec

    for role in COUNCIL_ROLES:
        spec = _stage_spec(role, "topic", None, "echo")
        _child, table = build_child_tools(
            MemoryStore(":memory:"), spec.tools, allow_dangerous=spec.allow_dangerous
        )
        assert all(t.risk != "dangerous" for t in table.values()), role


# -- G-20: autonomous dreams run a degraded grant set ---------------------------- #


def _make_methods() -> BridgeMethods:
    return BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
    )


def test_cron_dreams_have_no_dangerous_tools_at_all() -> None:
    methods = _make_methods()
    dream = methods._new_dream("echo", context="cron")
    ok, reason = dream.approval_policy.allows("run_shell", {"command": "echo hi"})
    assert not ok and reason == "unknown tool"
    # the context gate is the second layer, still in place
    assert dream.approval_policy.context == "cron"
    # non-dangerous tools keep working
    ok, reason = dream.approval_policy.allows("calculate", {"expression": "1+1"})
    assert ok


def test_single_query_dreams_are_degraded_the_same_way() -> None:
    methods = _make_methods()
    dream = methods._new_dream("echo", context="single_query")
    ok, reason = dream.approval_policy.allows(
        "send_email", {"to": "x", "subject": "s", "body": "b"}
    )
    assert not ok and reason == "unknown tool"


def test_interactive_dreams_keep_the_full_table() -> None:
    methods = _make_methods()
    dream = methods._new_dream("echo")
    ok, reason = dream.approval_policy.allows("run_shell", {"command": "echo hi"})
    assert not ok and "no approver" in reason  # known, engine-refused — not unknown


# -- G-18: session access fails closed -------------------------------------------- #

SESSION_METHODS = (
    "session.get",
    "session.delete",
    "session.rename",
    "session.configure",
    "conversation.send",
    "conversation.stop",
    "conversation.compact",
    "nudge.status",
)


def _invoke(handler, params):
    if inspect.iscoroutinefunction(handler):
        return asyncio.run(handler(params))
    return handler(params)


@pytest.mark.parametrize("method", SESSION_METHODS)
def test_unknown_session_ids_are_refused_before_dispatch(method: str) -> None:
    methods = _make_methods()
    params = {"session_id": "sess_does_not_exist_00000000"}
    if method == "conversation.send":
        params["message"] = "hello"
    if method == "conversation.compact":
        params["reason"] = "manual"
    with pytest.raises(BridgeError):
        _invoke(methods.handlers[method], params)


def test_wrongly_typed_session_ids_are_refused_too() -> None:
    methods = _make_methods()
    for method in SESSION_METHODS:
        for bad in (123, ["x"], {"id": "x"}):
            with pytest.raises(BridgeError):
                _invoke(methods.handlers[method], {"session_id": bad, "message": "m"})


def test_session_ids_are_unguessable() -> None:
    methods = _make_methods()
    created = methods.session_create({"title": "probe"})
    session_id = created.get("session_id") or created.get("id")
    assert isinstance(session_id, str) and session_id.startswith("sess_")
    suffix = session_id[len("sess_"):]
    assert len(suffix) == 20
    int(suffix, 16)  # hex-only → 80 bits of entropy, no enumeration


def test_cross_session_access_never_leaks_another_sessions_store() -> None:
    methods = _make_methods()
    a = methods.session_create({"title": "a"})["session_id"]
    b = methods.session_create({"title": "b"})["session_id"]
    # a session's own id resolves; a malformed id never resolves to a store
    assert methods.session_get({"session_id": a})["id"] == a
    assert methods.session_get({"session_id": b})["id"] == b
    with pytest.raises(BridgeError):
        methods.session_get({"session_id": f"{a}tampered"})
