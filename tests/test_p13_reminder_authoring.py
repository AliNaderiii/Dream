"""P-13 — reminder authoring: schedule ``kind`` + one-off ``max_runs`` contract.

Reminders are schedules of ``kind='reminder'`` executed by the one existing
daemon; these tests pin that contract without touching real time, the network,
or any provider. Clocks are fixed or injectable, stores are temporary, and the
bridge is exercised against ``BridgeMethods`` exactly like
``test_bridge_subagent_schedule.py``.
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore
from dream.scheduler import (
    SCHEDULE_KINDS,
    SchedulerDaemon,
    create_schedule,
    ensure_schedule_tables,
    list_schedules,
    update_schedule,
)


@pytest.fixture()
def store() -> Any:
    store = MemoryStore(":memory:")
    ensure_schedule_tables(store)
    yield store
    store.close()


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------- kinds


def test_kind_round_trip_and_serialisation(store: MemoryStore) -> None:
    task = create_schedule(store, name="t", prompt="p", cron_expression="0 9 * * *")
    reminder = create_schedule(
        store, name="r", prompt="p", cron_expression="0 10 * * *", kind="reminder"
    )
    assert task.kind == "task"
    assert reminder.kind == "reminder"
    assert SCHEDULE_KINDS == frozenset({"task", "reminder"})
    wire = reminder_to_wire(reminder)
    assert wire["kind"] == "reminder"
    assert wire["exhausted"] is False


def reminder_to_wire(reminder: Any) -> dict[str, Any]:
    from dream.scheduler import schedule_to_dict

    return schedule_to_dict(reminder)


def test_kind_filters_the_list(store: MemoryStore) -> None:
    create_schedule(store, name="t1", prompt="p", cron_expression="0 9 * * *")
    create_schedule(
        store, name="r1", prompt="p", cron_expression="0 10 * * *", kind="reminder"
    )
    create_schedule(
        store, name="r2", prompt="p", cron_expression="0 11 * * *", kind="reminder"
    )
    assert [s.name for s in list_schedules(store, kind="reminder")] == ["r1", "r2"]
    assert [s.name for s in list_schedules(store, kind="task")] == ["t1"]
    assert len(list_schedules(store)) == 3  # unfiltered keeps both kinds


def test_kind_can_be_changed_by_update(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="t", prompt="p", cron_expression="0 9 * * *")
    updated = update_schedule(store, schedule.id, kind="reminder")
    assert updated is not None and updated.kind == "reminder"
    assert list_schedules(store, kind="task") == []


def test_invalid_kind_is_rejected_before_persistence(store: MemoryStore) -> None:
    existing = create_schedule(store, name="e", prompt="p", cron_expression="0 9 * * *")
    with pytest.raises(ValueError, match="kind must be one of"):
        create_schedule(store, name="x", prompt="p", cron_expression="0 9 * * *", kind="bogus")
    with pytest.raises(ValueError, match="kind must be one of"):
        create_schedule(store, name="x", prompt="p", cron_expression="0 9 * * *", kind=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="kind must be one of"):
        list_schedules(store, kind="bogus")
    with pytest.raises(ValueError, match="kind must be one of"):
        update_schedule(store, existing.id, kind="bogus")
    # Nothing was written by the rejected creates, and the existing row kept
    # its kind.
    assert [s.kind for s in list_schedules(store)] == ["task"]


def test_legacy_schema_migrates_idempotently_and_defaults_to_task() -> None:
    """A pre-P-13 database gains the kind column and every row reads 'task'."""
    path = Path(tempfile.mkdtemp()) / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE schedules (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'local',
            name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            cron_expression TEXT NOT NULL, natural_language TEXT NOT NULL DEFAULT '',
            prompt TEXT NOT NULL, session_id TEXT,
            enabled INTEGER NOT NULL DEFAULT 1, last_run REAL, next_run REAL,
            created_at REAL NOT NULL, max_runs INTEGER,
            run_count INTEGER NOT NULL DEFAULT 0,
            require_approval INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        "INSERT INTO schedules (id, name, cron_expression, prompt, created_at)"
        " VALUES ('legacy', 'old', '0 9 * * *', 'p', 1)"
    )
    conn.commit()
    conn.close()

    first = MemoryStore(str(path))
    ensure_schedule_tables(first)
    rows = list_schedules(first)
    assert [r.id for r in rows] == ["legacy"]
    assert rows[0].kind == "task"
    # Idempotence: a second open on the same file must not fail or duplicate.
    ensure_schedule_tables(first)
    assert list_schedules(first)[0].kind == "task"
    first.close()

    second = MemoryStore(str(path))
    ensure_schedule_tables(second)
    assert [s.kind for s in list_schedules(second)] == ["task"]
    # New writes after migration still work and carry the kind.
    created = create_schedule(
        second, name="r", prompt="p", cron_expression="0 9 * * *", kind="reminder"
    )
    assert created.kind == "reminder"
    second.close()


# ------------------------------------------------------- max_runs contract


def test_once_to_repeat_clears_max_runs(store: MemoryStore) -> None:
    schedule = create_schedule(
        store,
        name="r",
        prompt="p",
        cron_expression="30 9 20 3 *",
        max_runs=1,
        kind="reminder",
    )
    assert schedule.max_runs == 1
    updated = update_schedule(
        store, schedule.id, natural_language="every day at 9 AM", max_runs=None
    )
    assert updated is not None
    assert updated.max_runs is None  # the cap is cleared, not kept
    assert updated.cron_expression == "0 9 * * *"


def test_once_to_once_preserves_max_runs(store: MemoryStore) -> None:
    schedule = create_schedule(
        store, name="r", prompt="p", cron_expression="30 9 20 3 *", max_runs=1
    )
    updated = update_schedule(store, schedule.id, max_runs=1, cron_expression="0 10 21 3 *")
    assert updated is not None
    assert updated.max_runs == 1
    assert updated.exhausted is False


def test_repeat_to_once_sets_max_runs(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="r", prompt="p", cron_expression="0 9 * * *")
    assert schedule.max_runs is None
    updated = update_schedule(
        store, schedule.id, cron_expression="0 10 21 3 *", max_runs=1
    )
    assert updated is not None
    assert updated.max_runs == 1


def test_omitted_max_runs_preserves_the_previous_value(store: MemoryStore) -> None:
    schedule = create_schedule(
        store, name="r", prompt="p", cron_expression="0 9 * * *", max_runs=5
    )
    updated = update_schedule(store, schedule.id, name="renamed")
    assert updated is not None
    assert updated.max_runs == 5
    assert updated.name == "renamed"


def test_invalid_max_runs_is_rejected_before_persistence(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="r", prompt="p", cron_expression="0 9 * * *")
    with pytest.raises(ValueError, match="max_runs must be at least 1"):
        update_schedule(store, schedule.id, max_runs=0)
    with pytest.raises(ValueError, match="max_runs must be at least 1"):
        create_schedule(store, name="x", prompt="p", cron_expression="0 9 * * *", max_runs=-2)
    with pytest.raises((TypeError, ValueError)):
        update_schedule(store, schedule.id, max_runs="many")  # type: ignore[arg-type]
    reloaded = list_schedules(store)[0]
    assert reloaded.max_runs is None  # unchanged by the rejected patches


def test_p12_update_callers_remain_backward_compatible(store: MemoryStore) -> None:
    """The pre-P-12/P-12 kwarg style (no kind, no explicit null) still works."""
    schedule = create_schedule(store, name="t", prompt="p", cron_expression="0 9 * * *")
    updated = update_schedule(
        store,
        schedule.id,
        name="t2",
        prompt="p2",
        enabled=False,
        require_approval=True,
        max_runs=3,
    )
    assert updated is not None
    assert (updated.name, updated.prompt, updated.enabled, updated.require_approval) == (
        "t2",
        "p2",
        False,
        True,
    )
    assert updated.max_runs == 3
    assert updated.kind == "task"  # untouched by a kind-unaware caller


# ------------------------------------------------------- one-off semantics


def force_due(store: MemoryStore, schedule: Any) -> None:
    """Mark a schedule due now, the same way the P-12 suite does."""
    import time as _time

    from dream.scheduler import get_schedule

    with store._lock:  # noqa: SLF001
        store.conn.execute(
            "UPDATE schedules SET next_run = ? WHERE id = ?", (_time.time() - 1, schedule.id)
        )
        store.conn.commit()
    assert get_schedule(store, schedule.id) is not None


def test_one_off_cron_fires_exactly_once_then_finishes(store: MemoryStore) -> None:
    """`M H D Mon *` + max_runs=1: the daemon fires it once and it exhausts."""
    from dream.scheduler import get_schedule, list_runs

    reminder = create_schedule(
        store,
        name="renew insurance",
        prompt="Reminder: renew insurance",
        cron_expression="0 9 20 3 *",
        max_runs=1,
        kind="reminder",
    )
    assert reminder.exhausted is False
    force_due(store, reminder)

    fired: list[str] = []

    def runner(schedule: Any) -> str:
        fired.append(schedule.prompt)
        return "ran"

    async def scenario() -> list[str]:
        daemon = SchedulerDaemon(store=store, runner=runner)
        first = await daemon.tick()
        await daemon.stop()  # drains the in-flight run to completion
        # The executed reminder is exhausted now; nothing is due a second time.
        second = await daemon.tick()
        return first + second

    launched = run(scenario())
    assert launched == [reminder.id]  # exactly one launch
    assert fired == ["Reminder: renew insurance"]
    final = get_schedule(store, reminder.id)
    assert final is not None
    assert final.run_count == 1
    assert final.exhausted is True
    assert [r.status for r in list_runs(store, schedule_id=reminder.id)] == ["success"]


def test_reminder_uses_the_single_existing_daemon(store: MemoryStore) -> None:
    """A reminder rides the same tick as a task — one worker, one pass."""
    task = create_schedule(store, name="t", prompt="task prompt", cron_expression="0 9 * * *")
    reminder = create_schedule(
        store,
        name="r",
        prompt="reminder prompt",
        cron_expression="0 9 * * *",
        kind="reminder",
    )
    force_due(store, task)
    force_due(store, reminder)
    fired: list[str] = []

    def runner(schedule: Any) -> str:
        fired.append(schedule.prompt)
        return "ok"

    async def scenario() -> list[str]:
        daemon = SchedulerDaemon(store=store, runner=runner)
        launched = await daemon.tick()
        await daemon.stop()
        return launched

    launched = run(scenario())
    assert sorted(launched) == sorted([task.id, reminder.id])
    assert sorted(fired) == ["reminder prompt", "task prompt"]


def test_reminder_approval_gate_fails_closed(store: MemoryStore) -> None:
    """A reminder that needs approval and is denied never runs (fail-closed)."""
    from dream.scheduler import get_schedule, list_runs

    reminder = create_schedule(
        store,
        name="r",
        prompt="p",
        cron_expression="0 9 * * *",
        kind="reminder",
        require_approval=True,
    )
    force_due(store, reminder)
    fired: list[str] = []

    async def denying_gate(_: Any) -> bool:
        await asyncio.sleep(0)  # cooperative yield; the decision is deny
        return False

    def runner(schedule: Any) -> str:
        fired.append(schedule.prompt)
        return "ran"

    async def scenario() -> None:
        daemon = SchedulerDaemon(
            store=store,
            runner=runner,
            approval_gate=denying_gate,
            approval_timeout=0.05,
        )
        await daemon.tick()
        await daemon.stop()  # drains the denied run's history row

    run(scenario())
    assert fired == []  # fail-closed: never executed
    runs = list_runs(store, schedule_id=reminder.id)
    assert [r.status for r in runs] == ["approval_denied"]
    final = get_schedule(store, reminder.id)
    # The claim consumed the slot (P-12 semantics: the schedule advanced even
    # though the run was denied), but nothing executed.
    assert final is not None and final.run_count == 1
    assert final.last_run is not None


# ---------------------------------------------------------------- bridge


def make_methods(**kwargs: Any) -> BridgeMethods:
    store = MemoryStore(":memory:")
    return BridgeMethods(
        store,
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
        **kwargs,
    )


def test_bridge_creates_and_lists_reminders_by_kind() -> None:
    m = make_methods()
    created = m.schedule_create(
        {
            "name": "renew insurance",
            "prompt": "Reminder: renew insurance",
            "cron_expression": "0 9 20 3 *",
            "max_runs": 1,
            "kind": "reminder",
        }
    )
    assert created["kind"] == "reminder"
    listed = m.schedule_list({"kind": "reminder"})
    assert [s["schedule_id"] for s in listed["schedules"]] == [created["schedule_id"]]
    assert m.schedule_list({"kind": "task"})["schedules"] == []


def test_bridge_defaults_to_task_and_stays_compatible() -> None:
    m = make_methods()
    created = m.schedule_create({"name": "t", "prompt": "p", "cron_expression": "0 9 * * *"})
    assert created["kind"] == "task"  # absent kind → P-12 behaviour unchanged
    assert [s["kind"] for s in m.schedule_list({})["schedules"]] == ["task"]


def test_bridge_rejects_invalid_kind_and_bad_max_runs() -> None:
    m = make_methods()
    with pytest.raises(BridgeError):
        m.schedule_create(
            {"name": "x", "prompt": "p", "cron_expression": "0 9 * * *", "kind": "bogus"}
        )
    with pytest.raises(BridgeError):
        m.schedule_list({"kind": "bogus"})
    with pytest.raises(BridgeError):
        m.schedule_update({"schedule_id": "sch_missing", "kind": "bogus"})
    # Nothing was persisted by the rejected create.
    assert m.schedule_list({})["schedules"] == []


def test_bridge_max_runs_three_way_contract() -> None:
    """Omitted keeps, JSON null clears, integer sets — over the wire."""
    m = make_methods()
    created = m.schedule_create(
        {
            "name": "r",
            "prompt": "p",
            "cron_expression": "0 9 20 3 *",
            "max_runs": 1,
            "kind": "reminder",
        }
    )
    sid = created["schedule_id"]

    # omitted → preserved
    kept = m.schedule_update({"schedule_id": sid, "name": "renamed"})
    assert kept["max_runs"] == 1

    # explicit null → cleared (once → repeat)
    cleared = m.schedule_update(
        {"schedule_id": sid, "natural_language": "every day at 9 AM", "max_runs": None}
    )
    assert cleared["max_runs"] is None
    assert cleared["cron_expression"] == "0 9 * * *"

    # integer → set again (repeat → once)
    again = m.schedule_update(
        {"schedule_id": sid, "cron_expression": "0 10 21 3 *", "max_runs": 1}
    )
    assert again["max_runs"] == 1


def test_reminder_preview_is_deterministic_and_truthful() -> None:
    from dream.scheduler import preview_schedule, upcoming_runs

    preview = preview_schedule(cron_expression="0 9 20 3 *")
    assert preview["valid"] is True
    assert preview["cron_expression"] == "0 9 20 3 *"
    moment = datetime(2026, 3, 19, 12, 0)
    runs = upcoming_runs("0 9 20 3 *", count=2, after=moment.timestamp())
    assert [datetime.fromtimestamp(r).strftime("%Y-%m-%d %H:%M") for r in runs] == [
        "2026-03-20 09:00",
        "2027-03-20 09:00",
    ]
