"""RPC surface for ``subagent.*`` and ``schedule.*`` (P-06).

Subagents live in asyncio Tasks on the loop that spawned them, so each test
does all of its work inside a single ``asyncio.run`` — mirroring the sidecar,
which has one long-lived loop for the life of the process.
"""

from __future__ import annotations

import asyncio
import tempfile
from typing import Any

import pytest

from dream.agent import EchoBackend
from dream.bridge.errors import RESOURCE_EXHAUSTED, BridgeError
from dream.bridge.methods import BridgeMethods
from dream.bridge.streams import Stream
from dream.memory import MemoryStore


def make_methods(**kwargs: Any) -> BridgeMethods:
    store = MemoryStore(":memory:")
    return BridgeMethods(
        store,
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
        **kwargs,
    )


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def wait_terminal(m: BridgeMethods, sub_id: str, tries: int = 400) -> dict[str, Any]:
    for _ in range(tries):
        state = m.subagent_get({"subagent_id": sub_id})
        if state["status"] not in {"idle", "running", "paused"}:
            return state
        await asyncio.sleep(0.01)
    return m.subagent_get({"subagent_id": sub_id})


# ============================================================== subagent.spawn


def test_spawn_returns_a_registered_subagent() -> None:
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.subagent_spawn(
            {"prompt": "summarise this", "name": "summariser", "tools": ["calculate"]}
        )
        state = await wait_terminal(m, spawned["subagent_id"])
        return spawned, state

    spawned, state = run(scenario())
    assert spawned["subagent_id"].startswith("sub_")
    assert spawned["name"] == "summariser"
    assert "log" not in spawned  # the list shape stays light
    assert state["status"] == "completed"
    assert state["result"] == "Echo: summarise this"
    assert state["turn_count"] == 1


def test_spawn_accepts_the_legacy_message_alias() -> None:
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.subagent_spawn({"message": "hi"})
        return await wait_terminal(m, spawned["subagent_id"])

    assert run(scenario())["result"] == "Echo: hi"


@pytest.mark.parametrize("params", [{}, {"prompt": ""}, {"prompt": "   "}, {"prompt": 7}])
def test_spawn_rejects_a_missing_prompt(params: dict[str, Any]) -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="prompt"):
        run(m.subagent_spawn(params))


def test_spawn_rejects_malformed_tools() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="tools"):
        run(m.subagent_spawn({"prompt": "go", "tools": "calculate"}))


@pytest.mark.parametrize(
    ("key", "value"),
    [("max_turns", 0), ("max_turns", "many"), ("max_duration", 0), ("max_tokens", -1)],
)
def test_spawn_rejects_invalid_limits(key: str, value: Any) -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match=key):
        run(m.subagent_spawn({"prompt": "go", key: value}))


def test_spawn_carries_the_configured_limits() -> None:
    m = make_methods()

    async def scenario() -> Any:
        return await m.subagent_spawn(
            {"prompt": "go", "max_turns": 3, "max_tokens": 500, "max_duration": 12.5}
        )

    spawned = run(scenario())
    assert (spawned["max_turns"], spawned["max_tokens"], spawned["max_duration"]) == (
        3,
        500,
        12.5,
    )


def test_concurrency_cap_reports_resource_exhausted() -> None:
    """G3: the cap is an RPC-visible error, not a silent queue."""
    m = make_methods()
    m.subagents.max_concurrent = 1

    async def scenario() -> None:
        await m.subagent_spawn({"prompt": "slow one", "max_duration": 5})
        await m.subagent_spawn({"prompt": "too many"})

    with pytest.raises(BridgeError) as excinfo:
        run(scenario())
    assert excinfo.value.code == RESOURCE_EXHAUSTED


# =============================================== subagent.list / get / status


def test_list_is_newest_first_and_reports_active_count() -> None:
    m = make_methods()

    async def scenario() -> Any:
        await m.subagent_spawn({"prompt": "first"})
        await m.subagent_spawn({"prompt": "second"})
        return m.subagent_list({})

    listed = run(scenario())
    assert [s["prompt"] for s in listed["subagents"]] == ["second", "first"]
    assert listed["active"] >= 0


def test_list_filters_by_session() -> None:
    m = make_methods()

    async def scenario() -> Any:
        await m.subagent_spawn({"prompt": "mine", "session_id": "sess_a"})
        await m.subagent_spawn({"prompt": "theirs", "session_id": "sess_b"})
        return m.subagent_list({"session_id": "sess_a"})

    listed = run(scenario())
    assert [s["prompt"] for s in listed["subagents"]] == ["mine"]


def test_get_includes_the_log_and_status_is_an_alias() -> None:
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.subagent_spawn({"prompt": "hello"})
        await wait_terminal(m, spawned["subagent_id"])
        got = m.subagent_get({"subagent_id": spawned["subagent_id"]})
        alias = m.subagent_status({"subagent_id": spawned["subagent_id"]})
        return got, alias

    got, alias = run(scenario())
    assert got["log"]
    assert {"ts", "level", "message"} <= set(got["log"][0])
    assert alias["status"] == got["status"]


@pytest.mark.parametrize("method", ["subagent_get", "subagent_pause", "subagent_resume"])
def test_unknown_subagent_id_is_invalid_params(method: str) -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="no subagent with id"):
        getattr(m, method)({"subagent_id": "sub_nope"})


def test_missing_subagent_id_is_rejected() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="subagent_id"):
        m.subagent_get({})


# ================================================ cancel / pause / resume


def test_cancel_returns_a_terminal_subagent_quickly() -> None:
    """G6: cancel must settle well inside the two-second budget."""
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.subagent_spawn({"prompt": "long job", "max_duration": 30})
        started = asyncio.get_event_loop().time()
        cancelled = await m.subagent_cancel({"subagent_id": spawned["subagent_id"]})
        return cancelled, asyncio.get_event_loop().time() - started

    cancelled, seconds = run(scenario())
    assert cancelled["cancelled"] is True
    assert cancelled["status"] in {"cancelled", "completed"}
    assert seconds < 2.0


def test_cancel_of_an_unknown_id_is_invalid_params() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="no subagent with id"):
        run(m.subagent_cancel({"subagent_id": "sub_nope"}))


def test_pause_then_resume_round_trips() -> None:
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.subagent_spawn({"prompt": "work", "max_duration": 30})
        sub_id = spawned["subagent_id"]
        paused = m.subagent_pause({"subagent_id": sub_id})
        resumed = m.subagent_resume({"subagent_id": sub_id})
        await m.subagent_cancel({"subagent_id": sub_id})
        return paused, resumed

    paused, resumed = run(scenario())
    assert paused["status"] == "paused"
    assert resumed["status"] == "running"


def test_resuming_a_running_subagent_is_rejected() -> None:
    m = make_methods()

    async def scenario() -> None:
        spawned = await m.subagent_spawn({"prompt": "work", "max_duration": 30})
        try:
            m.subagent_resume({"subagent_id": spawned["subagent_id"]})
        finally:
            await m.subagent_cancel({"subagent_id": spawned["subagent_id"]})

    with pytest.raises(BridgeError, match="not paused"):
        run(scenario())


# ================================================================= pipeline


def test_pipeline_chains_each_stage_into_the_next() -> None:
    """G5: a stage's output becomes the following stage's context."""
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.subagent_pipeline(
            {"stages": [{"prompt": "research"}, {"prompt": "summarise"}]}
        )
        for sub in spawned["subagents"]:
            await wait_terminal(m, sub["subagent_id"])
        return spawned, m.subagent_list({"pipeline_id": spawned["pipeline_id"]})

    spawned, listed = run(scenario())
    assert spawned["pipeline_id"].startswith("pipe_")
    assert len(spawned["subagents"]) == 2
    states = {s["pipeline_index"]: s for s in listed["subagents"]}
    assert states[0]["status"] == "completed"
    assert states[1]["context"] == states[0]["result"]


@pytest.mark.parametrize("stages", [None, [], "nope", [{"prompt": "ok"}, "bad"]])
def test_pipeline_rejects_malformed_stages(stages: Any) -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="stages"):
        run(m.subagent_pipeline({"stages": stages}))


# ==================================================================== logs


def test_logs_stream_replays_history_then_ends() -> None:
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.subagent_spawn({"prompt": "hello"})
        stream = await m.subagent_logs({"subagent_id": spawned["subagent_id"]})
        assert isinstance(stream, Stream)
        chunks = [chunk async for chunk in stream.chunks]
        return stream, chunks

    stream, chunks = run(scenario())
    assert stream.final["status"] in {"running", "completed", "idle"}
    assert chunks, "expected at least the spawn log line"
    assert all(chunk["token"] == chunk["entry"]["message"] for chunk in chunks)


def test_logs_of_an_unknown_subagent_is_invalid_params() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="no subagent with id"):
        run(m.subagent_logs({"subagent_id": "sub_nope"}))


# ============================================================= schedule.*


def test_schedule_create_from_natural_language() -> None:
    m = make_methods()
    created = m.schedule_create(
        {"name": "Morning brief", "prompt": "summarise", "natural_language": "every day at 9 AM"}
    )
    assert created["cron_expression"] == "0 9 * * *"
    assert created["human"] == "every day at 9:00 AM"
    assert created["enabled"] is True
    assert created["next_run"] is not None


def test_schedule_create_rejects_unparseable_prose() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="could not understand"):
        m.schedule_create({"name": "x", "prompt": "p", "natural_language": "whenever"})


@pytest.mark.parametrize(
    "params",
    [
        {"prompt": "p", "natural_language": "every day at 9 AM"},
        {"name": "x", "natural_language": "every day at 9 AM"},
        {"name": "  ", "prompt": "p", "natural_language": "every day at 9 AM"},
    ],
)
def test_schedule_create_requires_name_and_prompt(params: dict[str, Any]) -> None:
    m = make_methods()
    with pytest.raises(BridgeError):
        m.schedule_create(params)


def test_schedule_list_get_update_toggle_delete() -> None:
    m = make_methods()
    created = m.schedule_create(
        {"name": "A", "prompt": "go", "cron_expression": "0 9 * * *"}
    )
    sid = created["schedule_id"]

    assert [s["schedule_id"] for s in m.schedule_list({})["schedules"]] == [sid]

    got = m.schedule_get({"schedule_id": sid})
    assert got["name"] == "A"
    assert got["runs"] == []

    updated = m.schedule_update(
        {"schedule_id": sid, "name": "B", "natural_language": "every 15 minutes"}
    )
    assert updated["name"] == "B"
    assert updated["cron_expression"] == "*/15 * * * *"

    assert m.schedule_toggle({"schedule_id": sid})["enabled"] is False
    assert m.schedule_toggle({"schedule_id": sid, "enabled": True})["enabled"] is True

    assert m.schedule_delete({"schedule_id": sid}) == {"deleted": True, "schedule_id": sid}
    assert m.schedule_list({})["schedules"] == []


def test_schedule_list_can_hide_disabled() -> None:
    m = make_methods()
    created = m.schedule_create({"name": "A", "prompt": "go", "cron_expression": "0 9 * * *"})
    m.schedule_toggle({"schedule_id": created["schedule_id"], "enabled": False})
    assert m.schedule_list({"include_disabled": False})["schedules"] == []
    assert len(m.schedule_list({})["schedules"]) == 1


def test_schedule_update_rejects_a_bad_cron() -> None:
    m = make_methods()
    created = m.schedule_create({"name": "A", "prompt": "go", "cron_expression": "0 9 * * *"})
    with pytest.raises(BridgeError):
        m.schedule_update({"schedule_id": created["schedule_id"], "cron_expression": "99 * * * *"})


@pytest.mark.parametrize(
    "method", ["schedule_get", "schedule_update", "schedule_delete", "schedule_toggle"]
)
def test_unknown_schedule_id_is_invalid_params(method: str) -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="no schedule with id"):
        getattr(m, method)({"schedule_id": "sch_nope"})


def test_missing_schedule_id_is_rejected() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="schedule_id"):
        m.schedule_get({})


# =========================================================== preview / history


def test_preview_translates_prose() -> None:
    m = make_methods()
    preview = m.schedule_preview({"natural_language": "every weekday at 6 PM"})
    assert preview["valid"] is True
    assert preview["cron_expression"] == "0 18 * * 1-5"
    assert preview["human"] == "every weekday at 6:00 PM"


def test_preview_reports_failure_without_raising() -> None:
    m = make_methods()
    preview = m.schedule_preview({"natural_language": "at some point"})
    assert preview["valid"] is False
    assert preview["error"]


def test_preview_accepts_the_text_alias_and_empty_input() -> None:
    m = make_methods()
    assert m.schedule_preview({"text": "every 15 minutes"})["cron_expression"] == "*/15 * * * *"
    assert m.schedule_preview({})["valid"] is False


def test_run_now_executes_and_logs_history() -> None:
    """G10: an execution leaves a history row with a status and a duration."""
    m = make_methods()
    created = m.schedule_create({"name": "A", "prompt": "hello", "cron_expression": "0 3 * * *"})
    sid = created["schedule_id"]

    outcome = run(m.schedule_run_now({"schedule_id": sid}))
    assert outcome["run"]["status"] == "success"
    assert outcome["run"]["result_summary"] == "Echo: hello"
    assert outcome["run"]["duration"] >= 0

    history = m.schedule_history({"schedule_id": sid})
    assert [r["status"] for r in history["runs"]] == ["success"]


def test_run_now_reuses_an_existing_session() -> None:
    m = make_methods()
    session = m.session_create({"title": "Reports"})
    created = m.schedule_create(
        {
            "name": "A",
            "prompt": "hello",
            "cron_expression": "0 3 * * *",
            "session_id": session["session_id"],
        }
    )
    run(m.schedule_run_now({"schedule_id": created["schedule_id"]}))
    assert m.session_get({"session_id": session["session_id"]})["message_count"] == 1


def test_history_across_all_schedules_is_limited() -> None:
    m = make_methods()
    first = m.schedule_create({"name": "A", "prompt": "hello", "cron_expression": "0 3 * * *"})
    second = m.schedule_create({"name": "B", "prompt": "world", "cron_expression": "0 4 * * *"})
    run(m.schedule_run_now({"schedule_id": first["schedule_id"]}))
    run(m.schedule_run_now({"schedule_id": second["schedule_id"]}))

    assert len(m.schedule_history({})["runs"]) == 2
    assert len(m.schedule_history({"limit": 1})["runs"]) == 1
    assert len(m.schedule_history({"schedule_id": first["schedule_id"]})["runs"]) == 1


def test_history_rejects_a_bad_limit() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="limit"):
        m.schedule_history({"limit": 0})


# ============================================================ approval gate


def test_approval_required_run_waits_then_proceeds_when_approved() -> None:
    """G8/G11: nothing runs until a human answers the pending approval."""
    m = make_methods()
    created = m.schedule_create(
        {
            "name": "Risky",
            "prompt": "delete everything",
            "cron_expression": "0 3 * * *",
            "require_approval": True,
        }
    )

    async def scenario() -> Any:
        task = asyncio.get_event_loop().create_task(
            m.schedule_run_now({"schedule_id": created["schedule_id"]})
        )
        for _ in range(200):  # wait for the gate to register its approval
            if m.approvals:
                break
            await asyncio.sleep(0.01)
        approval_id = next(iter(m.approvals))
        assert m.approvals[approval_id].name == "schedule.execute"
        m.schedule_approve({"approval_id": approval_id, "allowed": True})
        return await task

    outcome = run(scenario())
    assert outcome["run"]["status"] == "success"


def test_denied_approval_records_approval_denied() -> None:
    m = make_methods()
    created = m.schedule_create(
        {
            "name": "Risky",
            "prompt": "delete everything",
            "cron_expression": "0 3 * * *",
            "require_approval": True,
        }
    )

    async def scenario() -> Any:
        task = asyncio.get_event_loop().create_task(
            m.schedule_run_now({"schedule_id": created["schedule_id"]})
        )
        for _ in range(200):
            if m.approvals:
                break
            await asyncio.sleep(0.01)
        m.schedule_approve({"approval_id": next(iter(m.approvals)), "allowed": False})
        return await task

    outcome = run(scenario())
    assert outcome["run"]["status"] == "approval_denied"


def test_approve_rejects_an_unknown_approval() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="no approval with id"):
        m.schedule_approve({"approval_id": "appr_nope"})
    with pytest.raises(BridgeError, match="approval_id"):
        m.schedule_approve({})


# ============================================================ daemon wiring


def test_start_and_stop_scheduler() -> None:
    m = make_methods()

    async def scenario() -> None:
        daemon = m.start_scheduler()
        assert daemon.running is True
        m.start_scheduler()  # idempotent
        await m.stop_scheduler()
        assert daemon.running is False

    run(scenario())


def test_stop_scheduler_without_start_is_safe() -> None:
    run(make_methods().stop_scheduler())


# ============================================================= handler table


def test_every_new_method_is_routable() -> None:
    m = make_methods()
    expected = {
        "subagent.spawn",
        "subagent.pipeline",
        "subagent.list",
        "subagent.get",
        "subagent.status",
        "subagent.cancel",
        "subagent.pause",
            "subagent.resume",
            "subagent.logs",
            "council.run",
            "council.get",
            "schedule.create",
        "schedule.list",
        "schedule.get",
        "schedule.update",
        "schedule.delete",
        "schedule.toggle",
        "schedule.history",
        "schedule.preview",
        "schedule.run_now",
        "schedule.approve",
    }
    assert expected <= set(m.handlers)


def test_schedules_persist_across_a_restart() -> None:
    import pathlib

    path = pathlib.Path(tempfile.mkdtemp()) / "bridge.db"
    sessions = tempfile.mktemp(suffix=".json")
    providers = tempfile.mktemp(suffix=".json")

    first = BridgeMethods(
        MemoryStore(str(path)), sessions_path=sessions, providers_path=providers
    )
    created = first.schedule_create(
        {"name": "Persistent", "prompt": "go", "cron_expression": "0 9 * * *"}
    )
    first.shutdown()

    second = BridgeMethods(
        MemoryStore(str(path)), sessions_path=sessions, providers_path=providers
    )
    assert second.schedule_get({"schedule_id": created["schedule_id"]})["name"] == "Persistent"
    second.shutdown()


# ============================================================== council.*

async def wait_council_terminal(m: BridgeMethods, council_id: str, tries: int = 400) -> dict:
    for _ in range(tries):
        state = m.council_get({"council_id": council_id})
        if state["winner"] is not None:
            return state
        await asyncio.sleep(0.01)
    return m.council_get({"council_id": council_id})


def test_council_run_spawns_three_echo_members_in_order() -> None:
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.council_run({"prompt": "design the landing page"})
        done = await wait_council_terminal(m, spawned["council_id"])
        return spawned, done

    spawned, done = run(scenario())
    assert spawned["council_id"].startswith("council_")
    assert spawned["winner"] is None  # no silent fake winner before the judge runs
    assert [member["role"] for member in spawned["members"]] == [
        "proposer",
        "critic",
        "judge",
    ]
    assert all(member["provider"] == "echo" for member in spawned["members"])
    assert spawned["turns_consumed"] == 0  # local plan consumes nothing
    assert spawned["leaves_machine_any"] is False

    assert done["winner"] is not None
    judge = done["members"][2]
    assert done["winner"] == judge["result"]
    assert [member["status"] for member in done["members"]] == ["completed"] * 3


def test_council_run_rejects_a_missing_prompt() -> None:
    m = make_methods()

    async def scenario() -> Any:
        return await m.council_run({"prompt": ""})

    with pytest.raises(BridgeError):
        run(scenario())


def test_council_run_rejects_an_unknown_member_provider() -> None:
    m = make_methods()

    async def scenario() -> Any:
        return await m.council_run(
            {"prompt": "topic", "proposer": {"model_provider": "mystery"}}
        )

    with pytest.raises(BridgeError, match="unknown provider"):
        run(scenario())


def test_council_run_accepts_per_role_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    # An Aval member must not open a real connection in CI; the child's
    # backend is swapped for echo, provider metadata stays real.
    monkeypatch.setattr("dream.subagents._build_backend", lambda _spec: EchoBackend())
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.council_run(
            {
                "prompt": "topic",
                "proposer": {"model_provider": "echo", "model_name": "p-model"},
                "critic": {"model_provider": "aval", "model_name": "c-model"},
            }
        )
        return spawned

    spawned = run(scenario())
    assert spawned["members"][0]["provider"] == "echo"
    assert spawned["members"][0]["model"] == "p-model"
    assert spawned["members"][1]["provider"] == "aval"
    assert spawned["members"][1]["leaves_machine"] is True


def test_council_get_of_an_unknown_id_is_invalid_params() -> None:
    m = make_methods()

    async def scenario() -> Any:
        return m.council_get({"council_id": "council_nope"})

    with pytest.raises(BridgeError):
        run(scenario())


def test_council_children_are_real_subagents() -> None:
    m = make_methods()

    async def scenario() -> Any:
        spawned = await m.council_run({"prompt": "prioritise the backlog"})
        done = await wait_council_terminal(m, spawned["council_id"])
        listing = m.subagent_list({"pipeline_id": spawned["pipeline_id"]})
        return done, listing

    done, listing = run(scenario())
    assert len(listing["subagents"]) == 3
    pipeline_ids = {agent["pipeline_id"] for agent in listing["subagents"]}
    assert pipeline_ids == {done["pipeline_id"]}
