"""Stage E — cron/schedule storage hardening pins (G-21).

Schedules live in SQLite tables inside the session store. These tests pin
the storage invariants: parameterized SQL (injection attempts stay inert
literals), traversal-shaped fields never reach the filesystem, and the
scheduler hands prompts to the runner verbatim instead of deriving paths
from them.
"""

from __future__ import annotations

import asyncio

import pytest

from dream.memory import MemoryStore
from dream.scheduler import (
    SchedulerDaemon,
    create_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)

TRAVERSAL_SHAPES = (
    "../../etc/passwd",
    "..\\..\\windows\\system32",
    "/etc/shadow",
    "\\\\server\\share\\payload",
    "skills/../../../.ssh/id_rsa",
)


@pytest.mark.parametrize("payload", TRAVERSAL_SHAPES)
def test_traversal_shaped_prompts_are_stored_as_inert_literals(payload: str) -> None:
    with MemoryStore(":memory:") as store:
        schedule = create_schedule(
            store, name="probe", prompt=payload, cron_expression="0 9 * * *"
        )
        fetched = get_schedule(store, schedule.id)
        assert fetched is not None
        assert fetched.prompt == payload  # byte-identical, never interpreted


@pytest.mark.parametrize("payload", TRAVERSAL_SHAPES)
def test_traversal_shaped_session_ids_are_inert(payload: str) -> None:
    with MemoryStore(":memory:") as store:
        schedule = create_schedule(
            store,
            name="probe",
            prompt="say hello",
            cron_expression="0 9 * * *",
            session_id=payload,
        )
        fetched = get_schedule(store, schedule.id)
        assert fetched is not None and fetched.session_id == payload


def test_sql_injection_attempts_stay_literal_text() -> None:
    hostile_name = "x'); DROP TABLE schedules; --"
    hostile_prompt = "'); DELETE FROM schedules WHERE ('1'='1"
    with MemoryStore(":memory:") as store:
        schedule = create_schedule(
            store, name=hostile_name, prompt=hostile_prompt, cron_expression="0 9 * * *"
        )
        rows = list_schedules(store)
        assert len(rows) == 1
        assert rows[0].name == hostile_name
        assert rows[0].prompt == hostile_prompt
        # the tables survive the attempt
        assert get_schedule(store, schedule.id) is not None


def test_update_schedule_refuses_unknown_ids() -> None:
    with MemoryStore(":memory:") as store:
        assert update_schedule(store, "sched_does_not_exist", description="x") is None


def test_empty_name_or_prompt_is_refused() -> None:
    with MemoryStore(":memory:") as store:
        with pytest.raises(ValueError):
            create_schedule(store, name="", prompt="x", cron_expression="0 9 * * *")
        with pytest.raises(ValueError):
            create_schedule(store, name="x", prompt="   ", cron_expression="0 9 * * *")


def test_tick_runs_the_prompt_verbatim_and_writes_no_paths(tmp_path) -> None:
    seen: list[str] = []

    def runner(schedule) -> str:
        seen.append(schedule.prompt)
        return "done"

    async def scenario() -> None:
        with MemoryStore(str(tmp_path / "store.db")) as store:
            create_schedule(
                store,
                name="probe",
                prompt="../../etc/passwd",
                cron_expression="* * * * *",
            )
            daemon = SchedulerDaemon(store, runner=runner)
            schedule = list_schedules(store)[0]
            await daemon.run_now(schedule)

    asyncio.run(scenario())
    assert seen == ["../../etc/passwd"]  # verbatim to the runner
    # nothing materialised on disk beyond the store itself
    files = {p.name for p in tmp_path.rglob("*") if p.is_file()}
    assert files == {"store.db"}


def test_schedule_fields_round_trip_after_update() -> None:
    with MemoryStore(":memory:") as store:
        schedule = create_schedule(
            store, name="probe", prompt="first", cron_expression="0 9 * * *"
        )
        update_schedule(store, schedule.id, description="../weird/../value")
        fetched = get_schedule(store, schedule.id)
        assert fetched is not None
        assert fetched.description == "../weird/../value"
