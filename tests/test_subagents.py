"""Subagent lifecycle, resource limits, isolation and pipeline chaining."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from dream.memory import MemoryStore
from dream.subagents import (
    DEFAULT_TOOL_GRANT,
    SubAgent,
    SubAgentManager,
    SubAgentSpec,
    build_child_tools,
    estimate_tokens,
    subagent_to_dict,
)
from dream.tools import REGISTRY


class ScriptedBackend:
    """Returns queued responses, then repeats the last one forever."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[list[dict[str, Any]]] = []

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        del tools
        self.calls.append([dict(m) for m in messages])
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class SlowBackend:
    """Blocks for ``delay`` seconds, simulating a hung provider call."""

    def __init__(self, delay: float = 5.0) -> None:
        self.delay = delay
        self.calls = 0

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        del messages, tools
        self.calls += 1
        time.sleep(self.delay)
        return {"content": "slow answer", "tool_calls": []}


def answer(text: str) -> dict[str, Any]:
    return {"content": text, "tool_calls": []}


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "c1") -> dict[str, Any]:
    return {
        "content": None,
        "tool_calls": [{"id": call_id, "name": name, "arguments": arguments}],
    }


def spec(**overrides: Any) -> SubAgentSpec:
    base: dict[str, Any] = {"prompt": "summarise the notes", "name": "worker"}
    base.update(overrides)
    return SubAgentSpec(**base)


def patch_backend(monkeypatch: pytest.MonkeyPatch, backend: Any) -> None:
    monkeypatch.setattr("dream.subagents._build_backend", lambda _spec: backend)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------- G2


def test_spawn_runs_to_completion_and_captures_result(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("all done")]))

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        assert agent.status == "running"
        return await manager.wait(agent.id)

    finished = run(scenario())
    assert finished.status == "completed"
    assert finished.result == "all done"
    assert finished.error is None
    assert finished.turn_count == 1
    assert finished.finished_at is not None and finished.started_at is not None


def test_spawn_is_fire_and_forget(monkeypatch: pytest.MonkeyPatch) -> None:
    """``spawn`` returns before the child has produced anything."""
    patch_backend(monkeypatch, ScriptedBackend([answer("later")]))

    async def scenario() -> tuple[SubAgent, SubAgent]:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        immediate = SubAgent(**{**vars_of(agent)})
        return immediate, await manager.wait(agent.id)

    def vars_of(agent: SubAgent) -> dict[str, Any]:
        return {f: getattr(agent, f) for f in SubAgent.__slots__}

    immediate, finished = run(scenario())
    assert immediate.result is None
    assert finished.result == "later"


def test_cancel_marks_agent_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, SlowBackend(delay=5.0))

    async def scenario() -> tuple[SubAgent, float]:
        manager = SubAgentManager()
        agent = manager.spawn(spec(max_duration=30.0))
        await asyncio.sleep(0.05)
        started = time.monotonic()
        cancelled = await manager.cancel(agent.id, grace_seconds=0.2)
        return cancelled, time.monotonic() - started

    cancelled, took = run(scenario())
    assert cancelled.status == "cancelled"
    assert cancelled.error == "cancelled by parent"
    # Gate G6: the dashboard promises cancellation lands in under two seconds.
    assert took < 2.0


def test_cancel_before_first_turn_is_immediate(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("never seen")]))

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        return await manager.cancel(agent.id)

    assert run(scenario()).status == "cancelled"


def test_cancel_unknown_id_returns_none() -> None:
    async def scenario() -> Any:
        return await SubAgentManager().cancel("sub_missing")

    assert run(scenario()) is None


def test_cancel_is_idempotent_on_terminal_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("done")]))

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        await manager.wait(agent.id)
        return await manager.cancel(agent.id)

    finished = run(scenario())
    assert finished.status == "completed"
    assert finished.result == "done"


def test_pause_then_resume_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = ScriptedBackend(
        [tool_call("calculate", {"expression": "1+1"}), answer("two")]
    )
    patch_backend(monkeypatch, backend)

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec(max_duration=30.0))
        await asyncio.sleep(0.02)
        manager.pause(agent.id)
        assert manager.get(agent.id).status in ("paused", "completed")
        await asyncio.sleep(0.05)
        manager.resume(agent.id)
        return await manager.wait(agent.id)

    finished = run(scenario())
    assert finished.status == "completed"


def test_pause_does_not_consume_duration_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """A human reading the log must not burn the wall-clock budget."""
    patch_backend(monkeypatch, ScriptedBackend([answer("ok")]))

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec(max_duration=0.4))
        manager.pause(agent.id)
        await asyncio.sleep(0.6)  # longer than max_duration, but paused
        assert manager.get(agent.id).status == "paused"
        manager.resume(agent.id)
        return await manager.wait(agent.id)

    assert run(scenario()).status == "completed"


def test_pause_and_resume_are_noops_on_terminal_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("done")]))

    async def scenario() -> tuple[SubAgent, SubAgent]:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        await manager.wait(agent.id)
        return manager.pause(agent.id), manager.resume(agent.id)

    paused, resumed = run(scenario())
    assert paused.status == "completed"
    assert resumed.status == "completed"


def test_backend_failure_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def chat(self, messages: Any, tools: Any = None) -> dict[str, Any]:
            raise RuntimeError("provider exploded")

    patch_backend(monkeypatch, Broken())

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        return await manager.wait(agent.id)

    finished = run(scenario())
    assert finished.status == "failed"
    assert "provider exploded" in finished.error


# --------------------------------------------------------------------- G3


def test_turn_limit_produces_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([tool_call("calculate", {"expression": "1+1"})]))

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec(max_turns=3, max_duration=30.0))
        return await manager.wait(agent.id)

    finished = run(scenario())
    assert finished.status == "timeout"
    assert finished.limit_hit == "turns"
    assert finished.turn_count == 3


def test_token_limit_produces_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    long_answer = tool_call("calculate", {"expression": "2+2"})
    patch_backend(monkeypatch, ScriptedBackend([long_answer]))

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(
            spec(prompt="x" * 400, max_turns=100, max_tokens=60, max_duration=30.0)
        )
        return await manager.wait(agent.id)

    finished = run(scenario())
    assert finished.status == "timeout"
    assert finished.limit_hit == "tokens"


def test_duration_limit_interrupts_a_blocked_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """The watchdog fires even though the loop is stuck inside ``chat``."""
    patch_backend(monkeypatch, SlowBackend(delay=5.0))

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec(max_duration=0.2))
        return await manager.wait(agent.id, timeout=3.0)

    finished = run(scenario())
    assert finished.status == "timeout"
    assert finished.limit_hit == "duration"
    assert finished.elapsed() < 2.0


def test_spec_rejects_empty_prompt() -> None:
    with pytest.raises(ValueError, match="prompt must not be empty"):
        SubAgentSpec(prompt="   ")


def test_spec_clamps_limits_to_sane_minimums() -> None:
    tight = SubAgentSpec(prompt="go", max_turns=0, max_tokens=-5, max_duration=0.0)
    assert tight.max_turns == 1
    assert tight.max_tokens == 1
    assert tight.max_duration >= 0.05


def test_concurrency_cap_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, SlowBackend(delay=2.0))

    async def scenario() -> None:
        manager = SubAgentManager(max_concurrent=2)
        manager.spawn(spec(max_duration=10.0))
        manager.spawn(spec(max_duration=10.0))
        await asyncio.sleep(0.02)
        with pytest.raises(ResourceWarning, match="subagent limit reached"):
            manager.spawn(spec())
        await manager.cancel_all()

    run(scenario())


def test_progress_tracks_the_tightest_budget() -> None:
    agent = SubAgent(
        id="sub_1",
        name="w",
        parent_session_id=None,
        model_provider="echo",
        model_name="",
        system_prompt="",
        tools=[],
        prompt="p",
        context="",
        max_turns=10,
        max_tokens=100,
        max_duration=100.0,
    )
    agent.turn_count = 5
    agent.token_count = 80
    assert agent.progress() == pytest.approx(0.8)
    agent.status = "completed"
    assert agent.progress() == 1.0


def test_estimate_tokens_is_monotonic_and_bounded() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("x" * 400) == 100
    assert estimate_tokens("x" * 800) > estimate_tokens("x" * 400)


# --------------------------------------------------------------------- G4


def test_global_registry_is_unchanged_by_a_subagent(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("done")]))
    before = dict(REGISTRY)

    async def scenario() -> None:
        manager = SubAgentManager()
        agent = manager.spawn(spec(tools=["calculate", "remember_fact"]))
        await manager.wait(agent.id)

    run(scenario())
    assert dict(REGISTRY) == before
    assert all(REGISTRY[name] is before[name] for name in before)


def test_child_memory_writes_never_reach_the_parent_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_store = MemoryStore(":memory:")
    backend = ScriptedBackend(
        [
            tool_call("remember_fact", {"content": "child secret"}),
            answer("stored"),
        ]
    )
    patch_backend(monkeypatch, backend)

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec(tools=["remember_fact"], max_duration=30.0))
        return await manager.wait(agent.id)

    finished = run(scenario())
    assert finished.status == "completed"
    assert parent_store.recall("child secret") == []
    parent_store.close()


def test_parent_memory_tools_still_target_the_parent_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The classic hazard: a child must not rebind the parent's closures."""
    from dream.agent import Dream

    parent_store = MemoryStore(":memory:")
    Dream(store=parent_store)
    patch_backend(monkeypatch, ScriptedBackend([answer("done")]))

    async def scenario() -> None:
        manager = SubAgentManager()
        agent = manager.spawn(spec(tools=["remember_fact"]))
        await manager.wait(agent.id)

    run(scenario())
    REGISTRY["remember_fact"].function(content="parent fact")
    assert [m.content for m in parent_store.recall("parent fact")] == ["parent fact"]
    parent_store.close()


def test_two_subagents_do_not_share_a_store(monkeypatch: pytest.MonkeyPatch) -> None:
    stores: list[MemoryStore] = []

    def factory() -> MemoryStore:
        store = MemoryStore(":memory:")
        stores.append(store)
        return store

    patch_backend(monkeypatch, ScriptedBackend([answer("done")]))

    async def scenario() -> None:
        manager = SubAgentManager(store_factory=factory)
        first = manager.spawn(spec(name="a"))
        second = manager.spawn(spec(name="b"))
        await manager.wait(first.id)
        await manager.wait(second.id)

    run(scenario())
    assert len(stores) == 2
    assert stores[0] is not stores[1]


def test_ungranted_tool_is_reported_as_not_granted(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = ScriptedBackend(
        [tool_call("run_shell", {"command": "rm -rf /"}), answer("blocked")]
    )
    patch_backend(monkeypatch, backend)

    async def scenario() -> SubAgent:
        manager = SubAgentManager()
        agent = manager.spawn(spec(tools=["calculate"], max_duration=30.0))
        return await manager.wait(agent.id)

    finished = run(scenario())
    assert finished.status == "completed"
    tool_messages = [
        m for call in backend.calls for m in call if m.get("role") == "tool"
    ]
    assert any("not granted" in str(m.get("content")) for m in tool_messages)


def test_dangerous_tools_are_dropped_from_the_grant() -> None:
    store = MemoryStore(":memory:")
    _child, table = build_child_tools(store, ["calculate", "run_shell", "send_email"])
    assert "calculate" in table
    assert "run_shell" not in table
    assert "send_email" not in table
    store.close()


def test_dangerous_tools_stay_denied_even_when_explicitly_allowed() -> None:
    """G11: ``allow_dangerous`` widens the grant, never the approval."""
    store = MemoryStore(":memory:")
    child, table = build_child_tools(store, ["run_shell"], allow_dangerous=True)
    assert "run_shell" in table
    allowed, reason = child.approval_policy.allows("run_shell", {"command": "ls"})
    assert allowed is False
    assert "no approver configured" in reason
    store.close()


def test_unknown_tool_names_are_dropped_silently() -> None:
    store = MemoryStore(":memory:")
    _child, table = build_child_tools(store, ["calculate", "does_not_exist"])
    assert set(table) == {"calculate"}
    store.close()


def test_default_grant_excludes_every_dangerous_capability() -> None:
    store = MemoryStore(":memory:")
    _child, table = build_child_tools(store, None)
    assert set(table) == set(DEFAULT_TOOL_GRANT)
    assert all(t.risk != "dangerous" for t in table.values())
    store.close()


def test_child_policy_resolves_risk_from_its_private_table() -> None:
    store = MemoryStore(":memory:")
    child, _table = build_child_tools(store, ["calculate"])
    allowed, reason = child.approval_policy.allows("run_shell", {})
    assert allowed is False
    assert reason == "unknown tool"
    store.close()


def test_context_is_fenced_into_the_first_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = ScriptedBackend([answer("ok")])
    patch_backend(monkeypatch, backend)

    async def scenario() -> None:
        manager = SubAgentManager()
        agent = manager.spawn(spec(context="the parent knows X"))
        await manager.wait(agent.id)

    run(scenario())
    first_user = next(m for m in backend.calls[0] if m["role"] == "user")
    assert "<context>\nthe parent knows X\n</context>" in first_user["content"]
    assert first_user["content"].endswith("summarise the notes")


def test_system_prompt_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = ScriptedBackend([answer("ok")])
    patch_backend(monkeypatch, backend)

    async def scenario() -> None:
        manager = SubAgentManager()
        agent = manager.spawn(spec(system_prompt="You are terse."))
        await manager.wait(agent.id)

    run(scenario())
    assert backend.calls[0][0] == {"role": "system", "content": "You are terse."}


# --------------------------------------------------------------------- G5


def test_pipeline_chains_each_result_into_the_next_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Counting:
        def __init__(self) -> None:
            self.seen: list[str] = []
            self.index = 0

        def chat(self, messages: Any, tools: Any = None) -> dict[str, Any]:
            del tools
            self.seen.append(next(m["content"] for m in messages if m["role"] == "user"))
            self.index += 1
            return answer(f"result-{self.index}")

    backend = Counting()
    patch_backend(monkeypatch, backend)

    async def scenario() -> list[SubAgent]:
        manager = SubAgentManager()
        pipeline_id, _ = manager.spawn_pipeline(
            [spec(prompt="step one"), spec(prompt="step two"), spec(prompt="step three")],
            name="chain",
        )
        return await manager.wait_pipeline(pipeline_id)

    stages = run(scenario())
    assert [s.status for s in stages] == ["completed"] * 3
    assert [s.result for s in stages] == ["result-1", "result-2", "result-3"]
    assert "result-1" in backend.seen[1]
    assert "result-2" in backend.seen[2]
    assert "result-1" not in backend.seen[2]


def test_pipeline_stages_start_idle_and_run_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("ok")]))

    async def scenario() -> tuple[list[str], list[SubAgent]]:
        manager = SubAgentManager()
        pipeline_id, staged = manager.spawn_pipeline([spec(), spec(), spec()])
        immediate = [s.status for s in staged]
        return immediate, await manager.wait_pipeline(pipeline_id)

    immediate, stages = run(scenario())
    assert immediate == ["idle", "idle", "idle"]
    assert [s.pipeline_index for s in stages] == [0, 1, 2]
    assert len({s.pipeline_id for s in stages}) == 1


def test_pipeline_halts_when_a_stage_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailSecond:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages: Any, tools: Any = None) -> dict[str, Any]:
            del messages, tools
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("stage two exploded")
            return answer("fine")

    patch_backend(monkeypatch, FailSecond())

    async def scenario() -> list[SubAgent]:
        manager = SubAgentManager()
        pipeline_id, _ = manager.spawn_pipeline([spec(), spec(), spec()])
        return await manager.wait_pipeline(pipeline_id)

    stages = run(scenario())
    assert [s.status for s in stages] == ["completed", "failed", "cancelled"]
    assert stages[2].error == "upstream stage did not complete"


def test_empty_pipeline_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one stage"):
        SubAgentManager().spawn_pipeline([])


# ------------------------------------------------------------- observability


def test_follow_logs_replays_history_then_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("done")]))

    async def scenario() -> list[dict[str, Any]]:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        collected = [entry async for entry in manager.follow_logs(agent.id)]
        await manager.wait(agent.id)
        return collected

    entries = run(scenario())
    assert entries
    assert all(entry["event"] == "log" for entry in entries)
    assert any("spawned with tools" in entry["message"] for entry in entries)


def test_follow_logs_streams_until_the_agent_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("done")]))

    async def scenario() -> list[dict[str, Any]]:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        return [entry async for entry in manager.follow_logs(agent.id)]

    entries = run(scenario())
    assert any("status: completed" in entry["message"] for entry in entries)


def test_follow_logs_for_unknown_agent_yields_nothing() -> None:
    async def scenario() -> list[Any]:
        return [e async for e in SubAgentManager().follow_logs("sub_nope")]

    assert run(scenario()) == []


def test_list_returns_newest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("ok")]))

    async def scenario() -> list[str]:
        manager = SubAgentManager()
        first = manager.spawn(spec(name="first"))
        second = manager.spawn(spec(name="second"))
        await manager.wait(first.id)
        await manager.wait(second.id)
        return [a.name for a in manager.list()]

    assert run(scenario()) == ["second", "first"]


def test_get_unknown_id_returns_none() -> None:
    assert SubAgentManager().get("sub_nope") is None


def test_serialisation_round_trips_every_field(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, ScriptedBackend([answer("payload")]))

    async def scenario() -> dict[str, Any]:
        manager = SubAgentManager()
        agent = manager.spawn(spec())
        finished = await manager.wait(agent.id)
        return subagent_to_dict(finished)

    payload = run(scenario())
    assert payload["subagent_id"] == payload["id"]
    assert payload["status"] == "completed"
    assert payload["result"] == "payload"
    assert payload["progress"] == 1.0
    assert isinstance(payload["log"], list)
    assert set(payload) >= {"turn_count", "token_count", "elapsed", "limit_hit", "tools"}


def test_serialisation_can_omit_the_log() -> None:
    agent = SubAgent(
        id="sub_1",
        name="w",
        parent_session_id=None,
        model_provider="echo",
        model_name="",
        system_prompt="",
        tools=[],
        prompt="p",
        context="",
    )
    assert "log" not in subagent_to_dict(agent, include_log=False)


def test_cancel_all_stops_every_running_child(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_backend(monkeypatch, SlowBackend(delay=1.0))

    async def scenario() -> list[str]:
        manager = SubAgentManager()
        manager.spawn(spec(max_duration=10.0))
        manager.spawn(spec(max_duration=10.0))
        await asyncio.sleep(0.02)
        await manager.cancel_all()
        return [a.status for a in manager.list()]

    assert run(scenario()) == ["cancelled", "cancelled"]


def test_child_ledger_is_detached_even_under_a_metered_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """S10: a child never bills its own turns against the parent's ledger.

    ``Dream.__init__`` attaches a ledger from the environment, so
    ``build_child_tools`` overrides it with the caller's explicit ledger
    (``None`` by default). Otherwise a council — which consumes its member
    turns once, up front — would double-count every child turn.
    """
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    store = MemoryStore(":memory:")
    child, _table = build_child_tools(store, None)
    assert child.ledger is None
    assert not ledger_path.exists()
    store.close()
