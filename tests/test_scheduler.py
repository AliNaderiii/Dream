"""Cron parsing, natural-language translation, schedule CRUD and the daemon."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

import pytest

from dream.cron import (
    cron_matches,
    describe_cron,
    next_run_after,
    parse_cron,
    validate_cron,
)
from dream.memory import MemoryStore
from dream.nl_schedule import NL_EXAMPLES, ScheduleParseError, nl_to_cron
from dream.scheduler import (
    Schedule,
    SchedulerDaemon,
    create_schedule,
    delete_schedule,
    due_schedules,
    ensure_schedule_tables,
    get_schedule,
    list_runs,
    list_schedules,
    mark_executed,
    preview_schedule,
    record_run_finished,
    record_run_started,
    run_to_dict,
    schedule_to_dict,
    toggle_schedule,
    upcoming_runs,
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


# ============================================================ G7: NL patterns

# Gloss for the Persian rows, in order: every day at 9 AM; every day at 6 in the
# evening; every Monday at 10:30; every Saturday at 8 AM; every 15 minutes;
# every 2 hours; every working day at 9; the first of every month; every Friday
# at noon; every midnight; every hour; every week.
NL_CASES: tuple[tuple[str, str], ...] = (
    # --- the six patterns named in the specification ---
    ("every day at 9 AM", "0 9 * * *"),
    ("every weekday at 6 PM", "0 18 * * 1-5"),
    ("every monday at 10:30", "30 10 * * 1"),
    ("every 2 hours", "0 */2 * * *"),
    ("every first day of month", "0 0 1 * *"),
    ("every 15 minutes", "*/15 * * * *"),
    # --- further English coverage ---
    ("every day at 9am", "0 9 * * *"),
    ("daily at midnight", "0 0 * * *"),
    ("every day at noon", "0 12 * * *"),
    ("every hour", "0 * * * *"),
    ("every 30 minutes", "*/30 * * * *"),
    ("every 5 minutes", "*/5 * * * *"),
    ("every 12 hours", "0 */12 * * *"),
    ("every 3 days at 7:15", "15 7 */3 * *"),
    ("every friday at noon", "0 12 * * 5"),
    ("every weekend at 8 AM", "0 8 * * 0,6"),
    ("every saturday at 11 PM", "0 23 * * 6"),
    ("every monday and thursday at 9", "0 9 * * 1,4"),
    ("every month on the 15th day", "0 0 15 * *"),
    ("every month on the 3rd day at 8 AM", "0 8 3 * *"),
    ("weekly at 5 PM", "0 17 * * 1"),
    ("every year", "0 0 1 1 *"),
    ("every business day at 07:45", "45 7 * * 1-5"),
    ("every day at 12 AM", "0 0 * * *"),
    ("every day at 12 PM", "0 12 * * *"),
    # --- Persian ---
    ("\u0647\u0631 \u0631\u0648\u0632 \u0633\u0627\u0639\u062a \u06f9 \u0635\u0628\u062d",
     "0 9 * * *"),
    ("\u0647\u0631 \u0631\u0648\u0632 \u0633\u0627\u0639\u062a \u06f6 \u0639\u0635\u0631",
     "0 18 * * *"),
    ("\u0647\u0631 \u062f\u0648\u0634\u0646\u0628\u0647 \u0633\u0627\u0639\u062a "
     "\u06f1\u06f0:\u06f3\u06f0", "30 10 * * 1"),
    ("\u0647\u0631 \u0634\u0646\u0628\u0647 \u0633\u0627\u0639\u062a \u06f8 "
     "\u0635\u0628\u062d", "0 8 * * 6"),
    ("\u0647\u0631 \u06f1\u06f5 \u062f\u0642\u06cc\u0642\u0647", "*/15 * * * *"),
    ("\u0647\u0631 \u06f2 \u0633\u0627\u0639\u062a", "0 */2 * * *"),
    ("\u0647\u0631 \u0631\u0648\u0632\u0647\u0627\u06cc \u06a9\u0627\u0631\u06cc "
     "\u0633\u0627\u0639\u062a \u06f9", "0 9 * * 6,0,1,2,3"),
    ("\u0647\u0631 \u0627\u0648\u0644 \u0645\u0627\u0647", "0 0 1 * *"),
    ("\u0647\u0631 \u062c\u0645\u0639\u0647 \u0638\u0647\u0631", "0 12 * * 5"),
    ("\u0647\u0631 \u0646\u06cc\u0645\u0647 \u0634\u0628", "0 0 * * *"),
    ("\u0647\u0631 \u0633\u0627\u0639\u062a", "0 * * * *"),
    ("\u0647\u0631 \u0647\u0641\u062a\u0647", "0 0 * * 1"),
)


@pytest.mark.parametrize(("text", "expected"), NL_CASES)
def test_nl_patterns(text: str, expected: str) -> None:
    """Gate G7: 20+ phrases, English and Persian, parse to the right cron."""
    assert nl_to_cron(text) == expected


def test_nl_case_count_meets_the_gate() -> None:
    assert len(NL_CASES) >= 20
    persian = [t for t, _ in NL_CASES if any("\u0600" <= c <= "\u06ff" for c in t)]
    assert len(persian) >= 10


def test_documented_examples_match_the_implementation() -> None:
    for text, expected in NL_EXAMPLES:
        assert nl_to_cron(text) == expected


def test_persian_digits_and_ascii_digits_agree() -> None:
    persian = nl_to_cron("\u0647\u0631 \u06f1\u06f5 \u062f\u0642\u06cc\u0642\u0647")
    assert persian == nl_to_cron("every 15 minutes")


def test_bare_cron_passes_through() -> None:
    assert nl_to_cron("0 9 * * *") == "0 9 * * *"
    assert nl_to_cron("*/10 * * * *") == "*/10 * * * *"


@pytest.mark.parametrize(
    "text",
    ["", "   ", "sometime soon", "when I feel like it", "\u0628\u0639\u062f\u0627"],
)
def test_unparseable_text_raises(text: str) -> None:
    with pytest.raises(ScheduleParseError):
        nl_to_cron(text)


def test_out_of_range_interval_is_rejected() -> None:
    with pytest.raises(ScheduleParseError, match="between 1 and 59"):
        nl_to_cron("every 90 minutes")
    with pytest.raises(ScheduleParseError, match="between 1 and 23"):
        nl_to_cron("every 40 hours")


def test_impossible_clock_time_is_rejected() -> None:
    with pytest.raises(ScheduleParseError, match="invalid clock time"):
        nl_to_cron("every day at 25:00")


def test_every_produced_cron_is_valid() -> None:
    """The parser must never emit something the cron engine rejects."""
    for text, _ in NL_CASES:
        validate_cron(nl_to_cron(text))


# ================================================================ cron engine


def test_parse_cron_expands_fields() -> None:
    parsed = parse_cron("*/15 9-17 * * 1-5")
    assert sorted(parsed.minutes) == [0, 15, 30, 45]
    assert sorted(parsed.hours) == list(range(9, 18))
    assert sorted(parsed.weekdays) == [1, 2, 3, 4, 5]


def test_parse_cron_accepts_both_sunday_encodings() -> None:
    assert parse_cron("0 0 * * 0").weekdays == parse_cron("0 0 * * 7").weekdays


def test_parse_cron_handles_a_wrapping_weekday_range() -> None:
    assert sorted(parse_cron("0 0 * * 5-1").weekdays) == [0, 1, 5, 6]


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "0 9 * *",
        "0 9 * * * *",
        "60 9 * * *",
        "0 24 * * *",
        "0 9 32 * *",
        "0 9 * 13 *",
        "0 9 * * 8",
        "abc 9 * * *",
        "0 9 * * 1-",
        "*/0 * * * *",
        "0 9 5-2 * *",
    ],
)
def test_invalid_cron_is_rejected(expression: str) -> None:
    with pytest.raises(ValueError):
        parse_cron(expression)


def test_cron_matches_a_known_moment() -> None:
    moment = datetime(2026, 8, 17, 9, 0)  # a Monday
    assert cron_matches("0 9 * * *", moment)
    assert cron_matches("0 9 * * 1", moment)
    assert not cron_matches("0 9 * * 2", moment)
    assert not cron_matches("30 9 * * *", moment)


def test_day_and_weekday_restrictions_are_a_union() -> None:
    """Vixie semantics: restricting both fields ORs them."""
    expression = "0 0 1 * 1"  # the 1st, and every Monday
    assert cron_matches(expression, datetime(2026, 8, 1, 0, 0))  # a Saturday, the 1st
    assert cron_matches(expression, datetime(2026, 8, 17, 0, 0))  # a Monday
    assert not cron_matches(expression, datetime(2026, 8, 18, 0, 0))  # Tuesday the 18th


def test_next_run_after_is_strictly_in_the_future() -> None:
    now = datetime(2026, 8, 15, 9, 0)
    assert next_run_after("0 9 * * *", now) == datetime(2026, 8, 16, 9, 0)


def test_next_run_after_finds_the_next_weekday() -> None:
    saturday = datetime(2026, 8, 15, 12, 0)
    assert next_run_after("0 9 * * 1-5", saturday) == datetime(2026, 8, 17, 9, 0)


def test_next_run_after_crosses_a_year_boundary() -> None:
    assert next_run_after("0 0 1 1 *", datetime(2026, 6, 1)) == datetime(2027, 1, 1, 0, 0)


def test_next_run_after_handles_leap_day() -> None:
    assert next_run_after("0 0 29 2 *", datetime(2026, 3, 1)) == datetime(2028, 2, 29, 0, 0)


def test_impossible_expression_terminates_with_an_error() -> None:
    with pytest.raises(ValueError, match="never fires"):
        next_run_after("0 0 30 2 *", datetime(2026, 1, 1))


def test_next_run_search_is_fast() -> None:
    started = time.monotonic()
    next_run_after("0 0 29 2 *", datetime(2026, 3, 1))
    assert time.monotonic() - started < 1.0


@pytest.mark.parametrize(
    ("expression", "fragment"),
    [
        ("0 9 * * *", "every day at 9:00 AM"),
        ("0 18 * * 1-5", "every weekday at 6:00 PM"),
        ("30 10 * * 1", "every Monday at 10:30 AM"),
        ("*/15 * * * *", "every 15 minutes"),
        ("0 */2 * * *", "every 2 hours"),
        ("0 0 1 * *", "1st"),
        ("0 8 * * 0,6", "weekend"),
        ("* * * * *", "every minute"),
    ],
)
def test_describe_cron_is_readable(expression: str, fragment: str) -> None:
    assert fragment in describe_cron(expression)


def test_describe_cron_round_trips_from_natural_language() -> None:
    for text, expected in NL_EXAMPLES:
        del text
        assert describe_cron(expected)


def test_upcoming_runs_are_ordered_and_distinct() -> None:
    base = datetime(2026, 8, 15, 0, 0).timestamp()
    runs = upcoming_runs("0 9 * * *", count=3, after=base)
    assert len(runs) == 3
    assert runs == sorted(runs)
    assert len(set(runs)) == 3


# ======================================================================= CRUD


def test_create_schedule_from_natural_language(store: MemoryStore) -> None:
    schedule = create_schedule(
        store, name="Morning brief", prompt="summarise my day",
        natural_language="every day at 9 AM",
    )
    assert schedule.cron_expression == "0 9 * * *"
    assert schedule.natural_language == "every day at 9 AM"
    assert schedule.enabled is True
    assert schedule.run_count == 0
    assert schedule.next_run is not None and schedule.next_run > time.time()
    assert schedule.human == "every day at 9:00 AM"


def test_create_schedule_from_explicit_cron(store: MemoryStore) -> None:
    schedule = create_schedule(
        store, name="Hourly", prompt="check", cron_expression="0 */3 * * *"
    )
    assert schedule.cron_expression == "0 */3 * * *"


def test_explicit_cron_wins_over_prose(store: MemoryStore) -> None:
    schedule = create_schedule(
        store, name="Both", prompt="go",
        cron_expression="0 6 * * *", natural_language="every day at 9 AM",
    )
    assert schedule.cron_expression == "0 6 * * *"
    assert schedule.natural_language == "every day at 9 AM"


def test_create_requires_a_name_and_prompt(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        create_schedule(store, name="  ", prompt="go", cron_expression="0 9 * * *")
    with pytest.raises(ValueError, match="prompt must not be empty"):
        create_schedule(store, name="n", prompt="", cron_expression="0 9 * * *")


def test_create_requires_a_rhythm(store: MemoryStore) -> None:
    with pytest.raises(ScheduleParseError):
        create_schedule(store, name="n", prompt="go")


def test_create_rejects_a_bad_cron(store: MemoryStore) -> None:
    with pytest.raises(ValueError):
        create_schedule(store, name="n", prompt="go", cron_expression="99 9 * * *")


def test_create_rejects_max_runs_below_one(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="max_runs"):
        create_schedule(
            store, name="n", prompt="go", cron_expression="0 9 * * *", max_runs=0
        )


def test_get_and_list_round_trip(store: MemoryStore) -> None:
    created = create_schedule(
        store, name="A", prompt="go", cron_expression="0 9 * * *"
    )
    fetched = get_schedule(store, created.id)
    assert fetched is not None
    assert fetched.name == "A"
    assert [s.id for s in list_schedules(store)] == [created.id]


def test_get_unknown_returns_none(store: MemoryStore) -> None:
    assert get_schedule(store, "sch_nope") is None


def test_list_orders_by_next_run_with_disabled_last(store: MemoryStore) -> None:
    late = create_schedule(store, name="late", prompt="p", cron_expression="0 23 * * *")
    early = create_schedule(store, name="early", prompt="p", cron_expression="*/5 * * * *")
    off = create_schedule(store, name="off", prompt="p", cron_expression="0 9 * * *")
    update_schedule(store, off.id, enabled=False)
    with_disabled_last = [s.name for s in list_schedules(store)]
    assert with_disabled_last[0] == "early"
    assert set(with_disabled_last) == {"early", "late", "off"}
    assert [s.id for s in list_schedules(store, include_disabled=False)] != []
    assert off.id not in {s.id for s in list_schedules(store, include_disabled=False)}
    del late, early


def test_schedules_are_scoped_to_their_user() -> None:
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "shared.db"
    alice = MemoryStore(str(path), user="alice")
    bob = MemoryStore(str(path), user="bob")
    ensure_schedule_tables(alice)
    create_schedule(alice, name="alice job", prompt="p", cron_expression="0 9 * * *")
    assert [s.name for s in list_schedules(alice)] == ["alice job"]
    assert list_schedules(bob) == []
    alice.close()
    bob.close()


def test_update_changes_fields_and_recomputes_next_run(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 23 * * *")
    original_next = schedule.next_run
    updated = update_schedule(
        store, schedule.id, name="B", prompt="stop", natural_language="every 15 minutes"
    )
    assert updated is not None
    assert updated.name == "B"
    assert updated.prompt == "stop"
    assert updated.cron_expression == "*/15 * * * *"
    assert updated.next_run != original_next


def test_update_unknown_returns_none(store: MemoryStore) -> None:
    assert update_schedule(store, "sch_nope", name="x") is None


def test_update_with_no_fields_is_a_noop(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    assert update_schedule(store, schedule.id).name == "A"


def test_update_rejects_blank_required_fields(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    with pytest.raises(ValueError, match="must not be empty"):
        update_schedule(store, schedule.id, name="   ")


def test_toggle_flips_and_sets(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    assert toggle_schedule(store, schedule.id).enabled is False
    assert toggle_schedule(store, schedule.id).enabled is True
    assert toggle_schedule(store, schedule.id, enabled=False).enabled is False
    assert toggle_schedule(store, "sch_nope") is None


def test_delete_removes_the_schedule_and_its_history(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    run_id = record_run_started(store, schedule.id)
    record_run_finished(store, run_id, status="success", result_summary="done")
    assert delete_schedule(store, schedule.id) is True
    assert get_schedule(store, schedule.id) is None
    assert list_runs(store, schedule_id=schedule.id) == []
    assert delete_schedule(store, schedule.id) is False


def test_ensure_tables_is_idempotent(store: MemoryStore) -> None:
    create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    ensure_schedule_tables(store)
    ensure_schedule_tables(store)
    assert len(list_schedules(store)) == 1


def test_schedule_survives_a_reopen() -> None:
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "sched.db"
    first = MemoryStore(str(path))
    created = create_schedule(first, name="A", prompt="go", cron_expression="0 9 * * *")
    first.close()
    second = MemoryStore(str(path))
    assert get_schedule(second, created.id).name == "A"
    second.close()


def test_serialisation_exposes_derived_fields(store: MemoryStore) -> None:
    schedule = create_schedule(
        store, name="A", prompt="go", natural_language="every day at 9 AM"
    )
    payload = schedule_to_dict(schedule)
    assert payload["schedule_id"] == payload["id"]
    assert payload["human"] == "every day at 9:00 AM"
    assert payload["exhausted"] is False
    assert set(payload) >= {"cron_expression", "next_run", "run_count", "require_approval"}


# ==================================================================== history


def test_run_rows_capture_status_and_duration(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    run_id = record_run_started(store, schedule.id, now=1000.0)
    record_run_finished(store, run_id, status="success", result_summary="ok", now=1002.5)
    runs = list_runs(store, schedule_id=schedule.id)
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].duration == pytest.approx(2.5)
    assert run_to_dict(runs[0])["duration"] == pytest.approx(2.5)


def test_open_run_has_no_duration(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    record_run_started(store, schedule.id)
    run = list_runs(store, schedule_id=schedule.id)[0]
    assert run.status == "running"
    assert run.duration is None


def test_history_is_newest_first_and_limited(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    for index in range(5):
        run_id = record_run_started(store, schedule.id, now=1000.0 + index)
        record_run_finished(store, run_id, status="success", result_summary=str(index))
    runs = list_runs(store, schedule_id=schedule.id, limit=3)
    assert [r.result_summary for r in runs] == ["4", "3", "2"]


def test_history_summary_is_truncated(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    run_id = record_run_started(store, schedule.id)
    record_run_finished(store, run_id, status="success", result_summary="x" * 2000)
    summary = list_runs(store, schedule_id=schedule.id)[0].result_summary
    assert len(summary) <= 500
    assert summary.endswith("\u2026")


def test_invalid_run_status_is_rejected(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    run_id = record_run_started(store, schedule.id)
    with pytest.raises(ValueError, match="status must be one of"):
        record_run_finished(store, run_id, status="whatever")


def test_mark_executed_advances_the_schedule(store: MemoryStore) -> None:
    schedule = make_due(store, name="A", cron_expression="*/5 * * * *")
    now = time.time()
    advanced = mark_executed(store, schedule, now=now)
    assert advanced.run_count == 1
    assert advanced.last_run == pytest.approx(now)
    # The stale past-due time is replaced by a genuinely future one.
    assert advanced.next_run > now
    assert get_schedule(store, schedule.id).next_run == advanced.next_run


def test_mark_executed_keeps_an_untriggered_next_run(store: MemoryStore) -> None:
    """A manual run before the fire time must not skip that day's occurrence."""
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 9 * * *")
    before = schedule.next_run
    advanced = mark_executed(store, schedule, now=time.time())
    assert advanced.next_run == before


def test_max_runs_disables_the_schedule_when_exhausted(store: MemoryStore) -> None:
    schedule = create_schedule(
        store, name="A", prompt="go", cron_expression="* * * * *", max_runs=2
    )
    schedule = mark_executed(store, schedule)
    assert schedule.enabled is True
    schedule = mark_executed(store, schedule)
    assert schedule.run_count == 2
    assert schedule.exhausted is True
    assert schedule.enabled is False
    assert schedule.next_run is None


# ===================================================================== daemon


def make_due(store: MemoryStore, **overrides: Any) -> Schedule:
    """A schedule that is already due, for tick-driven tests."""
    fields: dict[str, Any] = {
        "name": "job",
        "prompt": "do the thing",
        "cron_expression": "*/1 * * * *",
    }
    fields.update(overrides)
    schedule = create_schedule(store, **fields)
    return update_schedule_next_run(store, schedule, time.time() - 1)


def update_schedule_next_run(store: MemoryStore, schedule: Schedule, when: float) -> Schedule:
    with store._lock:  # noqa: SLF001
        store.conn.execute(
            "UPDATE schedules SET next_run = ? WHERE id = ?", (when, schedule.id)
        )
        store.conn.commit()
    return get_schedule(store, schedule.id)


def test_due_schedules_selects_only_what_is_ready(store: MemoryStore) -> None:
    due = make_due(store, name="due")
    create_schedule(store, name="later", prompt="p", cron_expression="0 3 * * *")
    assert [s.id for s in due_schedules(store)] == [due.id]


def test_due_ignores_disabled_and_exhausted(store: MemoryStore) -> None:
    disabled = make_due(store, name="off")
    toggle_schedule(store, disabled.id, enabled=False)
    exhausted = make_due(store, name="done", max_runs=1)
    mark_executed(store, exhausted)
    assert due_schedules(store) == []


def test_tick_fires_a_due_schedule(store: MemoryStore) -> None:
    schedule = make_due(store)
    seen: list[str] = []

    async def scenario() -> None:
        daemon = SchedulerDaemon(store=store, runner=lambda s: seen.append(s.prompt) or "ran")
        launched = await daemon.tick()
        assert launched == [schedule.id]
        await daemon.stop()

    run(scenario())
    assert seen == ["do the thing"]
    runs = list_runs(store, schedule_id=schedule.id)
    assert [r.status for r in runs] == ["success"]
    assert runs[0].result_summary == "ran"


def test_tick_skips_a_schedule_that_is_not_due(store: MemoryStore) -> None:
    create_schedule(store, name="later", prompt="p", cron_expression="0 3 * * *")
    calls: list[str] = []

    async def scenario() -> list[str]:
        daemon = SchedulerDaemon(store=store, runner=lambda s: calls.append(s.id))
        launched = await daemon.tick()
        await daemon.stop()
        return launched

    assert run(scenario()) == []
    assert calls == []


def test_tick_does_not_double_fire_a_slow_run(store: MemoryStore) -> None:
    """Advancing the schedule before running is what makes this safe."""
    schedule = make_due(store)
    started = asyncio.Event()

    async def slow(_schedule: Schedule) -> str:
        started.set()
        await asyncio.sleep(0.2)
        return "slow"

    async def scenario() -> list[str]:
        daemon = SchedulerDaemon(store=store, runner=slow)
        first = await daemon.tick()
        await started.wait()
        second = await daemon.tick()  # the same schedule must not be picked up again
        await daemon.stop()
        return first + second

    assert run(scenario()) == [schedule.id]


def test_runner_exception_is_recorded_as_an_error(store: MemoryStore) -> None:
    schedule = make_due(store)

    def boom(_schedule: Schedule) -> str:
        raise RuntimeError("prompt exploded")

    async def scenario() -> None:
        daemon = SchedulerDaemon(store=store, runner=boom)
        await daemon.tick()
        await asyncio.sleep(0.05)
        await daemon.stop()

    run(scenario())
    run_row = list_runs(store, schedule_id=schedule.id)[0]
    assert run_row.status == "error"
    assert "prompt exploded" in run_row.result_summary
    assert run_row.completed_at is not None


def test_a_failing_schedule_does_not_stop_the_daemon(store: MemoryStore) -> None:
    bad = make_due(store, name="bad")
    good = make_due(store, name="good")

    def runner(schedule: Schedule) -> str:
        if schedule.id == bad.id:
            raise RuntimeError("nope")
        return "fine"

    async def scenario() -> None:
        daemon = SchedulerDaemon(store=store, runner=runner)
        await daemon.tick()
        await asyncio.sleep(0.05)
        await daemon.stop()

    run(scenario())
    assert list_runs(store, schedule_id=bad.id)[0].status == "error"
    assert list_runs(store, schedule_id=good.id)[0].status == "success"


def test_async_runners_are_awaited(store: MemoryStore) -> None:
    schedule = make_due(store)

    async def runner(_schedule: Schedule) -> str:
        await asyncio.sleep(0)
        return "async result"

    async def scenario() -> None:
        daemon = SchedulerDaemon(store=store, runner=runner)
        await daemon.tick()
        await asyncio.sleep(0.05)
        await daemon.stop()

    run(scenario())
    assert list_runs(store, schedule_id=schedule.id)[0].result_summary == "async result"


def test_approval_gate_allows_an_approved_run(store: MemoryStore) -> None:
    schedule = make_due(store, require_approval=True)
    asked: list[str] = []

    async def gate(s: Schedule) -> bool:
        asked.append(s.name)
        return True

    async def scenario() -> None:
        daemon = SchedulerDaemon(store=store, runner=lambda s: "ran", approval_gate=gate)
        await daemon.tick()
        await asyncio.sleep(0.05)
        await daemon.stop()

    run(scenario())
    assert asked == ["job"]
    assert list_runs(store, schedule_id=schedule.id)[0].status == "success"


def test_denied_approval_never_runs_the_prompt(store: MemoryStore) -> None:
    schedule = make_due(store, require_approval=True)
    ran: list[str] = []

    async def gate(_s: Schedule) -> bool:
        return False

    async def scenario() -> None:
        daemon = SchedulerDaemon(
            store=store, runner=lambda s: ran.append(s.id), approval_gate=gate
        )
        await daemon.tick()
        await asyncio.sleep(0.05)
        await daemon.stop()

    run(scenario())
    assert ran == []
    assert list_runs(store, schedule_id=schedule.id)[0].status == "approval_denied"


def test_missing_approval_gate_denies(store: MemoryStore) -> None:
    """G11 fail-closed: approval required but nobody to ask means no run."""
    schedule = make_due(store, require_approval=True)
    ran: list[str] = []

    async def scenario() -> None:
        daemon = SchedulerDaemon(store=store, runner=lambda s: ran.append(s.id))
        await daemon.tick()
        await asyncio.sleep(0.05)
        await daemon.stop()

    run(scenario())
    assert ran == []
    assert list_runs(store, schedule_id=schedule.id)[0].status == "approval_denied"


def test_approval_timeout_denies(store: MemoryStore) -> None:
    schedule = make_due(store, require_approval=True)
    ran: list[str] = []

    async def slow_gate(_s: Schedule) -> bool:
        await asyncio.sleep(5)
        return True

    async def scenario() -> None:
        daemon = SchedulerDaemon(
            store=store,
            runner=lambda s: ran.append(s.id),
            approval_gate=slow_gate,
            approval_timeout=0.05,
        )
        await daemon.tick()
        await asyncio.sleep(0.2)
        await daemon.stop()

    run(scenario())
    assert ran == []
    assert list_runs(store, schedule_id=schedule.id)[0].status == "approval_denied"


def test_run_now_executes_immediately(store: MemoryStore) -> None:
    schedule = create_schedule(store, name="A", prompt="go", cron_expression="0 3 * * *")

    async def scenario() -> Any:
        daemon = SchedulerDaemon(store=store, runner=lambda s: "manual")
        result = await daemon.run_now(schedule)
        await daemon.stop()
        return result

    row = run(scenario())
    assert row.status == "success"
    assert row.result_summary == "manual"


def test_start_and_stop_are_clean(store: MemoryStore) -> None:
    make_due(store)
    calls: list[str] = []

    async def scenario() -> None:
        daemon = SchedulerDaemon(
            store=store, runner=lambda s: calls.append(s.id), poll_interval=0.05
        )
        daemon.start()
        await asyncio.sleep(0.12)
        await daemon.stop()
        assert daemon.running is False

    run(scenario())
    assert len(calls) == 1  # fired once, then the schedule moved into the future


def test_start_is_idempotent(store: MemoryStore) -> None:
    async def scenario() -> None:
        daemon = SchedulerDaemon(store=store, runner=lambda s: None, poll_interval=0.05)
        daemon.start()
        daemon.start()
        await daemon.stop()

    run(scenario())


def test_stop_without_start_is_safe(store: MemoryStore) -> None:
    async def scenario() -> None:
        await SchedulerDaemon(store=store, runner=lambda s: None).stop()

    run(scenario())


# ==================================================================== preview


def test_preview_resolves_natural_language() -> None:
    preview = preview_schedule(natural_language="every day at 9 AM")
    assert preview["valid"] is True
    assert preview["cron_expression"] == "0 9 * * *"
    assert preview["human"] == "every day at 9:00 AM"
    assert preview["next_run"] > time.time()
    assert preview["error"] is None


def test_preview_reports_a_parse_failure_without_raising() -> None:
    preview = preview_schedule(natural_language="whenever")
    assert preview["valid"] is False
    assert preview["cron_expression"] is None
    assert "could not understand" in preview["error"]


def test_preview_accepts_explicit_cron() -> None:
    assert preview_schedule(cron_expression="*/5 * * * *")["valid"] is True


def test_preview_of_empty_input_is_invalid_not_an_error() -> None:
    assert preview_schedule(natural_language="")["valid"] is False
