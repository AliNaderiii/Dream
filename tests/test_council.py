"""S10 — the opt-in three-role council (proposer → critic → judge).

Everything here is offline and deterministic: council members default to the
echo backend, the demo never touches the council, and a metered plan consumes
the council's member turns exactly once (never once per child turn).

The council spawns asyncio Tasks on the caller's loop, so every scenario runs
all of its work inside a single ``asyncio.run`` — the same pattern the bridge
tests use — otherwise the pipeline task and the wait live on different loops.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from cli import main, run_demo
from dream.agent import EchoBackend, OpenAIBackend, build_backend
from dream.commerce import Ledger
from dream.council import (
    COUNCIL_MEMBER_COUNT,
    CouncilMemberSpec,
    CouncilSpec,
    _leaves_machine,
    _stage_spec,
    get_council,
    run_council,
)
from dream.memory import MemoryStore
from dream.subagents import DEFAULT_TOOL_GRANT, SubAgentManager, build_child_tools


def patch_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route every member's real provider onto the offline echo backend.

    Provider resolution and ``leaves_machine`` still use the real council
    logic; only the child's network call is swapped, so a hosted member in a
    test never opens a connection.
    """
    monkeypatch.setattr("dream.subagents._build_backend", lambda _spec: EchoBackend())


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# ------------------------------------------------------------- kernel: order


def test_echo_council_runs_three_roles_in_fixed_order() -> None:
    manager = SubAgentManager()

    async def scenario() -> tuple[str, str]:
        result = run_council(manager, CouncilSpec(prompt="Summarise the release notes"))
        assert [member.role for member in result.members] == ["proposer", "critic", "judge"]
        assert result.winner is None  # no silent fake winner before the judge runs
        assert result.turns_consumed == 0  # local plan consumes nothing
        await manager.wait_pipeline(result.pipeline_id, timeout=15.0)
        return result.council_id, result.pipeline_id

    council_id, pipeline_id = run(scenario())
    fresh = get_council(manager, council_id)
    assert fresh is not None
    assert [member.status for member in fresh.members] == ["completed"] * 3

    judge = fresh.members[2]
    assert judge.result is not None
    assert fresh.winner == judge.result

    # Each stage received the previous one's result as context.
    proposer, critic, _ = fresh.members
    assert proposer.result in critic.result
    assert critic.result in judge.result


def test_every_council_id_is_unique_and_get_returns_none_for_unknown() -> None:
    manager = SubAgentManager()

    async def scenario() -> tuple[str, str, str, str]:
        first = run_council(manager, CouncilSpec(prompt="one"))
        second = run_council(manager, CouncilSpec(prompt="two"))
        return first.council_id, second.council_id, first.pipeline_id, second.pipeline_id

    first_id, second_id, first_pipe, second_pipe = run(scenario())
    assert first_id != second_id
    assert first_pipe != second_pipe
    assert get_council(manager, "council_does-not-exist") is None


# -------------------------------------------------------------- refusal paths


@pytest.mark.parametrize("topic", ["", "   ", None])
def test_empty_topic_is_refused_without_spawning(topic: Any) -> None:
    manager = SubAgentManager()
    with pytest.raises(ValueError):
        run_council(manager, CouncilSpec(prompt=topic))
    assert manager.list() == []


def test_unknown_provider_refuses_the_whole_council_before_spawn() -> None:
    manager = SubAgentManager()
    with pytest.raises(ValueError, match="unknown provider"):
        run_council(
            manager,
            CouncilSpec(prompt="topic", critic=CouncilMemberSpec(model_provider="mystery")),
        )
    assert manager.list() == []


def test_refused_council_leaves_an_empty_ledger_untouched(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    manager = SubAgentManager()
    with pytest.raises(ValueError):
        run_council(
            manager,
            CouncilSpec(prompt="topic", proposer=CouncilMemberSpec(model_provider="mystery")),
        )
    assert manager.list() == []
    assert not ledger_path.exists()


# ------------------------------------------------------------------ tool grant


def test_council_member_grant_is_only_the_default_tool_grant() -> None:
    # A council member's spec carries tools=None, which means the child is
    # built with exactly DEFAULT_TOOL_GRANT and nothing else.
    store = MemoryStore(":memory:")
    _child, table = build_child_tools(store, None)
    assert set(table) == set(DEFAULT_TOOL_GRANT)
    assert all(tool.risk != "dangerous" for tool in table.values())
    store.close()


def test_stage_specs_never_ask_for_dangerous_tools() -> None:
    for role in ("proposer", "critic", "judge"):
        spec = _stage_spec(role, "topic", None, "echo")
        assert spec.tools is None  # None means DEFAULT_TOOL_GRANT only
        assert spec.allow_dangerous is False


def test_a_granted_dangerous_name_stays_fail_closed_without_approver() -> None:
    store = MemoryStore(":memory:")
    child, table = build_child_tools(store, ["run_shell"], allow_dangerous=True)
    assert "run_shell" in table
    allowed, _reason = child.approval_policy.allows("run_shell", {"command": "echo hi"})
    assert allowed is False


# --------------------------------------------------------------- privacy flags


def test_leaves_machine_flags_echo_and_ollama_local() -> None:
    assert _leaves_machine("echo") is False
    assert _leaves_machine("ollama") is False
    assert _leaves_machine("") is False


def test_leaves_machine_flags_hosted_and_aval_remote() -> None:
    assert _leaves_machine("openai") is True
    assert _leaves_machine("aval") is True
    assert _leaves_machine("avalai") is True


def test_member_records_expose_leaves_machine(monkeypatch) -> None:
    patch_backend(monkeypatch)
    manager = SubAgentManager()

    async def scenario() -> list[bool]:
        result = run_council(
            manager,
            CouncilSpec(
                prompt="topic",
                proposer=CouncilMemberSpec(model_provider="aval"),
                judge=CouncilMemberSpec(model_provider="openai"),
            ),
        )
        return [member.leaves_machine for member in result.members]

    leaves = run(scenario())
    assert leaves == [True, False, True]


def test_all_local_council_reports_leaves_machine_any_false(monkeypatch) -> None:
    patch_backend(monkeypatch)
    manager = SubAgentManager()

    async def scenario() -> list[bool]:
        result = run_council(
            manager,
            CouncilSpec(prompt="topic", critic=CouncilMemberSpec(model_provider="ollama")),
        )
        return [member.leaves_machine for member in result.members]

    leaves = run(scenario())
    assert leaves == [False, False, False]


# --------------------------------------------------------------- no live HTTP


def test_echo_council_never_opens_a_connection(monkeypatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("urlopen must not be called during an echo council")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    manager = SubAgentManager()

    async def scenario() -> tuple[str, str]:
        result = run_council(manager, CouncilSpec(prompt="plan the sprint"))
        await manager.wait_pipeline(result.pipeline_id, timeout=15.0)
        return result.council_id, result.pipeline_id

    council_id, _pipeline_id = run(scenario())
    fresh = get_council(manager, council_id)
    assert fresh is not None
    assert fresh.winner is not None


# ---------------------------------------------------------------------- quota


def test_metered_council_consumes_three_turns_once(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    real_consume = Ledger.consume

    def spy(self: Ledger, *args: Any, **kwargs: Any) -> int:
        calls.append((args, kwargs))
        return real_consume(self, *args, **kwargs)

    monkeypatch.setattr(Ledger, "consume", spy)

    manager = SubAgentManager()

    async def scenario() -> tuple[str, int]:
        result = run_council(manager, CouncilSpec(prompt="plan the quarter"))
        await manager.wait_pipeline(result.pipeline_id, timeout=15.0)
        return result.pipeline_id, result.turns_consumed

    _pipeline_id, turns = run(scenario())
    assert turns == COUNCIL_MEMBER_COUNT

    # Exactly one consume call, for all three members at once — never one per
    # child turn (children carry no ledger, so their turns add nothing).
    assert calls == [((), {"amount": COUNCIL_MEMBER_COUNT})]
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == COUNCIL_MEMBER_COUNT
    assert Ledger().usage()["used"] == COUNCIL_MEMBER_COUNT


def test_exhausted_guest_quota_refuses_with_persian_reply(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    ledger = Ledger()
    for _ in range(19):
        ledger.consume()

    manager = SubAgentManager()
    result = run_council(manager, CouncilSpec(prompt="topic"))
    assert result.refusal is not None
    assert any("\u0600" <= char <= "\u06FF" for char in result.refusal)
    assert result.members == ()
    assert result.winner is None
    assert manager.list() == []
    assert Ledger().usage()["used"] == 19  # nothing was appended


def test_local_plan_consumes_nothing_and_creates_no_ledger(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    fake_default = tmp_path / "dream-ledger.json"
    monkeypatch.setattr("dream.commerce.DEFAULT_LEDGER_PATH", str(fake_default))

    manager = SubAgentManager()

    async def scenario() -> int:
        result = run_council(manager, CouncilSpec(prompt="topic"))
        await manager.wait_pipeline(result.pipeline_id, timeout=15.0)
        return result.turns_consumed

    turns = run(scenario())
    assert turns == 0
    assert not fake_default.exists()


def test_child_ledger_is_detached_even_under_a_metered_plan(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    store = MemoryStore(":memory:")
    child, _table = build_child_tools(store, None)
    assert child.ledger is None  # the child can never bill its own turns


# ---------------------------------------------------------------- CLI surface


def test_run_demo_never_imports_or_runs_council(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "dream.council" or name.startswith("dream.council."):
            raise AssertionError("run_demo must never import dream.council")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    run_demo(":memory:", output=lambda _text: None)


def test_demo_flag_returns_zero_without_mentioning_council(capsys) -> None:
    assert main(["--demo"]) == 0
    captured = capsys.readouterr()
    assert "council" not in captured.out.lower()
    assert "council" not in captured.err.lower()


def test_council_flag_runs_an_echo_council(capsys) -> None:
    assert main(["--council", "choose a project name"]) == 0
    captured = capsys.readouterr()
    assert "[proposer]" in captured.out
    assert "[critic]" in captured.out
    assert "[judge]" in captured.out
    assert "winner:" in captured.out


# --------------------------------------------------------------- aval backend


def test_build_backend_aval_and_avalai_point_at_avalai(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AVALAI_API_KEY", raising=False)
    for kind in ("aval", "avalai"):
        backend = build_backend(kind)
        assert isinstance(backend, OpenAIBackend)
        assert backend.base_url == "https://api.avalai.ir/v1"


def test_build_backend_aval_honours_base_and_key_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.avalai.ir/v1")
    monkeypatch.setenv("AVALAI_API_KEY", "avalkey")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend = build_backend("aval")
    assert backend.base_url == "https://api.avalai.ir/v1"
    assert backend.api_key == "avalkey"

    monkeypatch.setenv("OPENAI_API_KEY", "primary")
    assert build_backend("avalai").api_key == "primary"
