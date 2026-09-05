"""Recurring prompts: schedule storage, execution history, and the daemon.

A schedule is a prompt Dream runs on a cron rhythm without a human present.
That absence shapes every decision here:

* the tables live in the same SQLite database as memories and reminders, so a
  schedule survives a restart and can be inspected with the same tools;
* every execution writes a history row *before* it runs, so a crash mid-run is
  visible afterwards rather than silently forgotten;
* ``require_approval`` gates the whole run behind a human decision, and the
  agent that eventually runs carries no approver, so a dangerous tool is
  refused even when the run itself was approved.

The daemon takes its runner as an argument. That keeps the polling logic
testable against a fake clock with no model provider anywhere in sight.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dream.cron import describe_cron, next_run_after, validate_cron
from dream.memory import MemoryStore
from dream.nl_schedule import ScheduleParseError, nl_to_cron

__all__ = [
    "RUN_STATUSES",
    "Schedule",
    "ScheduleRun",
    "SchedulerDaemon",
    "claim_due_schedule",
    "create_schedule",
    "delete_schedule",
    "ensure_schedule_tables",
    "get_schedule",
    "list_runs",
    "list_schedules",
    "mark_executed",
    "preview_schedule",
    "record_run_finished",
    "record_run_started",
    "recover_interrupted_runs",
    "schedule_to_dict",
    "toggle_schedule",
    "upcoming_runs",
    "update_schedule",
]

logger = logging.getLogger(__name__)

RUN_STATUSES: frozenset[str] = frozenset({"running", "success", "error", "approval_denied"})

DEFAULT_POLL_INTERVAL = 30.0
DEFAULT_APPROVAL_TIMEOUT = 300.0
DEFAULT_DRAIN_TIMEOUT = 10.0
SUMMARY_LIMIT = 500


@dataclass(slots=True)
class Schedule:
    """One recurring prompt."""

    id: str
    name: str
    description: str
    cron_expression: str
    natural_language: str
    prompt: str
    session_id: str | None
    enabled: bool
    last_run: float | None
    next_run: float | None
    created_at: float
    max_runs: int | None
    run_count: int
    require_approval: bool

    @property
    def exhausted(self) -> bool:
        return self.max_runs is not None and self.run_count >= self.max_runs

    @property
    def human(self) -> str:
        try:
            return describe_cron(self.cron_expression)
        except ValueError:
            return self.cron_expression


@dataclass(slots=True)
class ScheduleRun:
    """One execution of a schedule."""

    id: int
    schedule_id: str
    started_at: float
    completed_at: float | None
    result_summary: str
    status: str

    @property
    def duration(self) -> float | None:
        if self.completed_at is None:
            return None
        return max(0.0, self.completed_at - self.started_at)


def schedule_to_dict(schedule: Schedule) -> dict[str, Any]:
    """Serialise a schedule for the JSON-RPC wire, including derived fields."""
    return {
        "schedule_id": schedule.id,
        "id": schedule.id,
        "name": schedule.name,
        "description": schedule.description,
        "cron_expression": schedule.cron_expression,
        "natural_language": schedule.natural_language,
        "human": schedule.human,
        "prompt": schedule.prompt,
        "session_id": schedule.session_id,
        "enabled": schedule.enabled,
        "last_run": schedule.last_run,
        "next_run": schedule.next_run,
        "created_at": schedule.created_at,
        "max_runs": schedule.max_runs,
        "run_count": schedule.run_count,
        "require_approval": schedule.require_approval,
        "exhausted": schedule.exhausted,
    }


def run_to_dict(run: ScheduleRun) -> dict[str, Any]:
    """Serialise one execution-history row."""
    return {
        "id": run.id,
        "schedule_id": run.schedule_id,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "duration": run.duration,
        "result_summary": run.result_summary,
        "status": run.status,
    }


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------


def ensure_schedule_tables(store: MemoryStore) -> None:
    """Create the schedule tables if absent, then add any missing columns.

    Idempotent in the same style as the reminder tables: a database written by
    an older build gains the new columns in place rather than being migrated
    by a version number nobody remembers to bump.
    """
    with store._lock:  # noqa: SLF001 - the store's own locking convention
        store.conn.execute(
            """CREATE TABLE IF NOT EXISTS schedules (
                id               TEXT    PRIMARY KEY,
                user_id          TEXT    NOT NULL DEFAULT 'local',
                name             TEXT    NOT NULL,
                description      TEXT    NOT NULL DEFAULT '',
                cron_expression  TEXT    NOT NULL,
                natural_language TEXT    NOT NULL DEFAULT '',
                prompt           TEXT    NOT NULL,
                session_id       TEXT,
                enabled          INTEGER NOT NULL DEFAULT 1,
                last_run         REAL,
                next_run         REAL,
                created_at       REAL    NOT NULL,
                max_runs         INTEGER,
                run_count        INTEGER NOT NULL DEFAULT 0,
                require_approval INTEGER NOT NULL DEFAULT 0
            )"""
        )
        # ON DELETE CASCADE from the start: history rows belong to their
        # schedule and must not outlive it as orphans.
        store.conn.execute(
            """CREATE TABLE IF NOT EXISTS schedule_runs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id    TEXT    NOT NULL,
                started_at     REAL    NOT NULL,
                completed_at   REAL,
                result_summary TEXT    NOT NULL DEFAULT '',
                status         TEXT    NOT NULL DEFAULT 'running',
                FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
            )"""
        )
        columns = {row["name"] for row in store.conn.execute("PRAGMA table_info(schedules)")}
        additions = {
            "description": "TEXT NOT NULL DEFAULT ''",
            "natural_language": "TEXT NOT NULL DEFAULT ''",
            "session_id": "TEXT",
            "last_run": "REAL",
            "next_run": "REAL",
            "max_runs": "INTEGER",
            "run_count": "INTEGER NOT NULL DEFAULT 0",
            "require_approval": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, spec in additions.items():
            if column not in columns:
                store.conn.execute(f"ALTER TABLE schedules ADD COLUMN {column} {spec}")
        store.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedules_user ON schedules(user_id, enabled)"
        )
        store.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule "
            "ON schedule_runs(schedule_id, started_at DESC)"
        )
        store.conn.commit()


def _row_to_schedule(row: Any) -> Schedule:
    return Schedule(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        cron_expression=row["cron_expression"],
        natural_language=row["natural_language"] or "",
        prompt=row["prompt"],
        session_id=row["session_id"],
        enabled=bool(row["enabled"]),
        last_run=row["last_run"],
        next_run=row["next_run"],
        created_at=row["created_at"],
        max_runs=row["max_runs"],
        run_count=int(row["run_count"] or 0),
        require_approval=bool(row["require_approval"]),
    )


def _row_to_run(row: Any) -> ScheduleRun:
    return ScheduleRun(
        id=int(row["id"]),
        schedule_id=row["schedule_id"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        result_summary=row["result_summary"] or "",
        status=row["status"],
    )


def _compute_next_run(cron_expression: str, after: float | None = None) -> float:
    moment = datetime.fromtimestamp(after if after is not None else time.time())
    return next_run_after(cron_expression, moment).timestamp()


def resolve_cron(
    *, cron_expression: str | None = None, natural_language: str | None = None
) -> tuple[str, str]:
    """Resolve the pair ``(cron_expression, natural_language)`` from either input.

    An explicit cron wins over the prose, because a user who typed cron meant
    it; the prose is kept verbatim either way so the UI can show what was said.
    """
    text = (natural_language or "").strip()
    if cron_expression and cron_expression.strip():
        return validate_cron(cron_expression), text
    if not text:
        raise ScheduleParseError("a schedule needs either a cron expression or a description")
    return nl_to_cron(text), text


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


def create_schedule(
    store: MemoryStore,
    *,
    name: str,
    prompt: str,
    cron_expression: str | None = None,
    natural_language: str | None = None,
    description: str = "",
    session_id: str | None = None,
    enabled: bool = True,
    max_runs: int | None = None,
    require_approval: bool = False,
) -> Schedule:
    """Insert a schedule and compute its first fire time."""
    ensure_schedule_tables(store)
    name = (name or "").strip()
    if not name:
        raise ValueError("schedule name must not be empty")
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("schedule prompt must not be empty")
    if max_runs is not None:
        max_runs = int(max_runs)
        if max_runs < 1:
            raise ValueError("max_runs must be at least 1 when set")
    expression, spoken = resolve_cron(
        cron_expression=cron_expression, natural_language=natural_language
    )
    now = time.time()
    schedule = Schedule(
        id=f"sch_{secrets.token_hex(6)}",
        name=name,
        description=(description or "").strip(),
        cron_expression=expression,
        natural_language=spoken,
        prompt=prompt,
        session_id=session_id,
        enabled=bool(enabled),
        last_run=None,
        next_run=_compute_next_run(expression, now),
        created_at=now,
        max_runs=max_runs,
        run_count=0,
        require_approval=bool(require_approval),
    )
    with store._lock:  # noqa: SLF001
        store.conn.execute(
            """INSERT INTO schedules (
                id, user_id, name, description, cron_expression, natural_language, prompt,
                session_id, enabled, last_run, next_run, created_at, max_runs, run_count,
                require_approval
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                schedule.id,
                store.user_id,
                schedule.name,
                schedule.description,
                schedule.cron_expression,
                schedule.natural_language,
                schedule.prompt,
                schedule.session_id,
                int(schedule.enabled),
                schedule.last_run,
                schedule.next_run,
                schedule.created_at,
                schedule.max_runs,
                schedule.run_count,
                int(schedule.require_approval),
            ),
        )
        store.conn.commit()
    return schedule


def get_schedule(store: MemoryStore, schedule_id: str) -> Schedule | None:
    """Fetch one schedule belonging to the store's user."""
    ensure_schedule_tables(store)
    with store._lock:  # noqa: SLF001
        row = store.conn.execute(
            "SELECT * FROM schedules WHERE id = ? AND user_id = ?",
            (schedule_id, store.user_id),
        ).fetchone()
    return _row_to_schedule(row) if row else None


def list_schedules(store: MemoryStore, *, include_disabled: bool = True) -> list[Schedule]:
    """All schedules for the store's user, soonest first.

    Rows with no ``next_run`` (a disabled schedule) sort last rather than
    first, which is what a list ordered by "what happens next" should show.
    """
    ensure_schedule_tables(store)
    query = "SELECT * FROM schedules WHERE user_id = ?"
    params: list[Any] = [store.user_id]
    if not include_disabled:
        query += " AND enabled = 1"
    query += " ORDER BY next_run IS NULL, next_run ASC, created_at ASC"
    with store._lock:  # noqa: SLF001
        rows = list(store.conn.execute(query, params))
    return [_row_to_schedule(row) for row in rows]


def due_schedules(store: MemoryStore, *, now: float | None = None) -> list[Schedule]:
    """Enabled, unexhausted schedules whose next run has arrived."""
    moment = time.time() if now is None else now
    return [
        schedule
        for schedule in list_schedules(store, include_disabled=False)
        if schedule.next_run is not None and schedule.next_run <= moment and not schedule.exhausted
    ]


_UPDATABLE = (
    "name",
    "description",
    "prompt",
    "session_id",
    "enabled",
    "max_runs",
    "require_approval",
)


def update_schedule(
    store: MemoryStore,
    schedule_id: str,
    *,
    cron_expression: str | None = None,
    natural_language: str | None = None,
    **fields: Any,
) -> Schedule | None:
    """Patch a schedule in place, recomputing ``next_run`` if the rhythm changed."""
    existing = get_schedule(store, schedule_id)
    if existing is None:
        return None
    updates: dict[str, Any] = {}
    for key in _UPDATABLE:
        if key not in fields or fields[key] is None:
            continue
        value = fields[key]
        if key in ("name", "prompt"):
            value = str(value).strip()
            if not value:
                raise ValueError(f"schedule {key} must not be empty")
        elif key in ("enabled", "require_approval"):
            value = int(bool(value))
        elif key == "max_runs":
            value = int(value)
            if value < 1:
                raise ValueError("max_runs must be at least 1 when set")
        updates[key] = value

    if cron_expression or natural_language:
        expression, spoken = resolve_cron(
            cron_expression=cron_expression, natural_language=natural_language
        )
        updates["cron_expression"] = expression
        if spoken:
            updates["natural_language"] = spoken
        updates["next_run"] = _compute_next_run(expression)
    elif "enabled" in updates and updates["enabled"] and existing.next_run is None:
        # Re-enabling a schedule has to give it a future again.
        updates["next_run"] = _compute_next_run(existing.cron_expression)

    if not updates:
        return existing
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with store._lock:  # noqa: SLF001
        store.conn.execute(
            f"UPDATE schedules SET {assignments} WHERE id = ? AND user_id = ?",
            (*updates.values(), schedule_id, store.user_id),
        )
        store.conn.commit()
    return get_schedule(store, schedule_id)


def toggle_schedule(
    store: MemoryStore, schedule_id: str, *, enabled: bool | None = None
) -> Schedule | None:
    """Flip or set a schedule's enabled flag."""
    existing = get_schedule(store, schedule_id)
    if existing is None:
        return None
    target = (not existing.enabled) if enabled is None else bool(enabled)
    return update_schedule(store, schedule_id, enabled=target)


def delete_schedule(store: MemoryStore, schedule_id: str) -> bool:
    """Remove a schedule and, by cascade, its history."""
    ensure_schedule_tables(store)
    with store._lock:  # noqa: SLF001
        cursor = store.conn.execute(
            "DELETE FROM schedules WHERE id = ? AND user_id = ?",
            (schedule_id, store.user_id),
        )
        # The cascade needs foreign keys on; delete explicitly so history is
        # gone even against a connection where the pragma was reset.
        store.conn.execute("DELETE FROM schedule_runs WHERE schedule_id = ?", (schedule_id,))
        store.conn.commit()
        return cursor.rowcount > 0


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


def record_run_started(store: MemoryStore, schedule_id: str, *, now: float | None = None) -> int:
    """Open a history row before the work begins and return its id."""
    ensure_schedule_tables(store)
    started = time.time() if now is None else now
    with store._lock:  # noqa: SLF001
        cursor = store.conn.execute(
            "INSERT INTO schedule_runs (schedule_id, started_at, status) VALUES (?,?,'running')",
            (schedule_id, started),
        )
        store.conn.commit()
        return int(cursor.lastrowid or 0)


def record_run_finished(
    store: MemoryStore,
    run_id: int,
    *,
    status: str,
    result_summary: str = "",
    now: float | None = None,
) -> None:
    """Close a history row with its outcome."""
    if status not in RUN_STATUSES:
        raise ValueError(f"status must be one of {sorted(RUN_STATUSES)}, got {status!r}")
    completed = time.time() if now is None else now
    summary = (result_summary or "").strip()
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[: SUMMARY_LIMIT - 1] + "\u2026"
    with store._lock:  # noqa: SLF001
        store.conn.execute(
            "UPDATE schedule_runs SET completed_at = ?, status = ?, result_summary = ? "
            "WHERE id = ?",
            (completed, status, summary, run_id),
        )
        store.conn.commit()


def recover_interrupted_runs(store: MemoryStore, *, now: float | None = None) -> int:
    """Settle lingering 'running' rows left from an interrupted process on restart."""
    ensure_schedule_tables(store)
    moment = time.time() if now is None else now
    with store._lock:  # noqa: SLF001
        cursor = store.conn.execute(
            "UPDATE schedule_runs SET completed_at = ?, status = 'error', "
            "result_summary = 'execution interrupted by system restart' "
            "WHERE status = 'running'",
            (moment,),
        )
        store.conn.commit()
        return int(cursor.rowcount)


def list_runs(
    store: MemoryStore, *, schedule_id: str | None = None, limit: int = 50
) -> list[ScheduleRun]:
    """Execution history, newest first, optionally for one schedule."""
    ensure_schedule_tables(store)
    limit = max(1, min(int(limit), 500))
    query = "SELECT * FROM schedule_runs"
    params: list[Any] = []
    if schedule_id:
        query += " WHERE schedule_id = ?"
        params.append(schedule_id)
    query += " ORDER BY started_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with store._lock:  # noqa: SLF001
        rows = list(store.conn.execute(query, params))
    return [_row_to_run(row) for row in rows]


def claim_due_schedule(
    store: MemoryStore, schedule: Schedule, *, now: float | None = None
) -> bool:
    """Atomically claim a due schedule by advancing its next_run.

    Returns True if this worker claimed the schedule; False if another
    worker or concurrent tick already claimed or updated it.
    """
    ensure_schedule_tables(store)
    moment = time.time() if now is None else now
    run_count = schedule.run_count + 1
    exhausted = schedule.max_runs is not None and run_count >= schedule.max_runs
    next_run = None if exhausted else _compute_next_run(schedule.cron_expression, moment)
    with store._lock:  # noqa: SLF001
        if schedule.next_run is not None:
            cursor = store.conn.execute(
                "UPDATE schedules SET last_run = ?, run_count = ?, next_run = ?, enabled = ? "
                "WHERE id = ? AND user_id = ? AND enabled = 1 AND next_run = ?",
                (
                    moment,
                    run_count,
                    next_run,
                    int(schedule.enabled and not exhausted),
                    schedule.id,
                    store.user_id,
                    schedule.next_run,
                ),
            )
        else:
            cursor = store.conn.execute(
                "UPDATE schedules SET last_run = ?, run_count = ?, next_run = ?, enabled = ? "
                "WHERE id = ? AND user_id = ? AND enabled = 1 AND next_run IS NULL",
                (
                    moment,
                    run_count,
                    next_run,
                    int(schedule.enabled and not exhausted),
                    schedule.id,
                    store.user_id,
                ),
            )
        store.conn.commit()
        return bool(cursor.rowcount > 0)


def mark_executed(
    store: MemoryStore, schedule: Schedule, *, now: float | None = None
) -> Schedule | None:
    """Advance ``last_run``, ``run_count`` and ``next_run`` after an execution.

    A schedule that has hit ``max_runs`` is disabled and loses its ``next_run``
    rather than being deleted: the user asked for N runs, and the history of
    those runs stays reachable from a row they can still see.
    """
    ensure_schedule_tables(store)
    moment = time.time() if now is None else now
    run_count = schedule.run_count + 1
    exhausted = schedule.max_runs is not None and run_count >= schedule.max_runs
    next_run = None if exhausted else _compute_next_run(schedule.cron_expression, moment)
    with store._lock:  # noqa: SLF001
        store.conn.execute(
            "UPDATE schedules SET last_run = ?, run_count = ?, next_run = ?, enabled = ? "
            "WHERE id = ? AND user_id = ?",
            (
                moment,
                run_count,
                next_run,
                int(schedule.enabled and not exhausted),
                schedule.id,
                store.user_id,
            ),
        )
        store.conn.commit()
    return get_schedule(store, schedule.id)


# --------------------------------------------------------------------------
# Daemon
# --------------------------------------------------------------------------

#: ``(schedule) -> summary text``. May be sync or async; a raised exception
#: becomes an ``error`` history row.
ScheduleRunner = Callable[[Schedule], Any]

#: ``(schedule) -> bool``. Returns whether a human approved this run.
ApprovalGate = Callable[[Schedule], Awaitable[bool]]


@dataclass(slots=True)
class SchedulerDaemon:
    """Polls for due schedules and runs them.

    The clock is injectable so tests can drive it precisely, and ``tick`` is
    public so a test never has to wait on real time.
    """

    store: MemoryStore
    runner: ScheduleRunner
    poll_interval: float = DEFAULT_POLL_INTERVAL
    approval_gate: ApprovalGate | None = None
    approval_timeout: float = DEFAULT_APPROVAL_TIMEOUT
    clock: Callable[[], float] = time.time
    running: bool = False
    _stop: asyncio.Event | None = field(default=None, init=False, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _inflight: set[asyncio.Task[None]] = field(default_factory=set, init=False, repr=False)

    def start(self) -> None:
        """Begin polling on the running event loop."""
        if self.running:
            return
        ensure_schedule_tables(self.store)
        recover_interrupted_runs(self.store, now=self.clock())
        self.running = True
        self._stop = asyncio.Event()
        self._task = asyncio.get_event_loop().create_task(self._loop(), name="scheduler")

    async def stop(self, *, drain_timeout: float = DEFAULT_DRAIN_TIMEOUT) -> None:
        """Stop polling and let in-flight executions finish.

        Executions are drained rather than cancelled: a run that has already
        started owns a history row, and killing it mid-flight would both lose
        the work and leave that row stuck in ``running``. Anything still going
        after ``drain_timeout`` is cancelled, and ``_execute`` records the
        cancellation as an error so no row is left open.
        """
        self.running = False
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._inflight:
            pending = list(self._inflight)
            done, still_running = await asyncio.wait(pending, timeout=drain_timeout)
            del done
            for task in still_running:
                task.cancel()
            if still_running:
                await asyncio.gather(*still_running, return_exceptions=True)
        self._inflight.clear()

    async def _loop(self) -> None:
        assert self._stop is not None
        while self.running:
            await self.tick()
            # On 3.10 ``asyncio.TimeoutError`` is still its own class, so both
            # names have to be caught for ``wait_for`` timeouts.
            with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
                # An interruptible sleep: ``stop`` should not have to wait out
                # a full poll interval.
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                return

    async def tick(self) -> list[str]:
        """Run one polling pass. Never raises; returns the ids launched.

        A failure inside one schedule must not stop the daemon — the next poll
        has to happen regardless of what the last prompt did.
        """
        try:
            due = due_schedules(self.store, now=self.clock())
        except Exception:  # pragma: no cover - defensive
            logger.exception("scheduler could not read due schedules")
            return []
        launched: list[str] = []
        for schedule in due:
            # Advance the schedule atomically before running it, so a long execution
            # or concurrent worker cannot pick it up twice.
            if not claim_due_schedule(self.store, schedule, now=self.clock()):
                continue
            task = asyncio.get_event_loop().create_task(
                self._execute(schedule), name=f"schedule:{schedule.id}"
            )
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)
            launched.append(schedule.id)
        return launched

    async def run_now(self, schedule: Schedule) -> ScheduleRun | None:
        """Execute a schedule immediately and await its history row."""
        await self._execute(schedule)
        runs = list_runs(self.store, schedule_id=schedule.id, limit=1)
        return runs[0] if runs else None

    async def _execute(self, schedule: Schedule) -> None:
        run_id = record_run_started(self.store, schedule.id, now=self.clock())
        if schedule.require_approval:
            approved = await self._await_approval(schedule)
            if not approved:
                record_run_finished(
                    self.store,
                    run_id,
                    status="approval_denied",
                    result_summary="run was not approved",
                    now=self.clock(),
                )
                return
        try:
            outcome = self.runner(schedule)
            if asyncio.iscoroutine(outcome) or isinstance(outcome, asyncio.Future):
                outcome = await outcome
        except asyncio.CancelledError:
            record_run_finished(
                self.store,
                run_id,
                status="error",
                result_summary="execution cancelled",
                now=self.clock(),
            )
            raise
        except Exception as exc:
            logger.debug("schedule %s failed", schedule.id, exc_info=True)
            record_run_finished(
                self.store,
                run_id,
                status="error",
                result_summary=f"{type(exc).__name__}: {exc}",
                now=self.clock(),
            )
            return
        record_run_finished(
            self.store,
            run_id,
            status="success",
            result_summary="" if outcome is None else str(outcome),
            now=self.clock(),
        )

    async def _await_approval(self, schedule: Schedule) -> bool:
        """Ask for approval, denying on timeout or when no gate is configured.

        Fail-closed: an unattended prompt that nobody approved must not run.
        """
        if self.approval_gate is None:
            return False
        try:
            return bool(
                await asyncio.wait_for(
                    self.approval_gate(schedule), timeout=self.approval_timeout
                )
            )
        except (TimeoutError, asyncio.TimeoutError, asyncio.CancelledError):
            return False
        except Exception:  # pragma: no cover - a broken gate denies
            logger.exception("approval gate failed for schedule %s", schedule.id)
            return False


def preview_schedule(
    *, natural_language: str | None = None, cron_expression: str | None = None
) -> dict[str, Any]:
    """Resolve, describe and project a schedule without storing anything.

    Powers the live preview under the "add schedule" field: it always returns a
    payload rather than raising, because a half-typed phrase is the normal case
    while someone is typing, not an error worth a red banner.
    """
    try:
        expression, spoken = resolve_cron(
            cron_expression=cron_expression, natural_language=natural_language
        )
    except (ScheduleParseError, ValueError) as exc:
        return {
            "valid": False,
            "cron_expression": None,
            "human": None,
            "next_run": None,
            "natural_language": (natural_language or "").strip(),
            "error": str(exc),
        }
    return {
        "valid": True,
        "cron_expression": expression,
        "human": describe_cron(expression),
        "next_run": _compute_next_run(expression),
        "natural_language": spoken,
        "error": None,
    }


def upcoming_runs(
    cron_expression: str, *, count: int = 3, after: float | None = None
) -> list[float]:
    """The next ``count`` fire times, for the UI's "next runs" hint."""
    moment = datetime.fromtimestamp(after if after is not None else time.time())
    results: list[float] = []
    for _ in range(max(0, count)):
        moment = next_run_after(cron_expression, moment)
        results.append(moment.timestamp())
    return results


def summarise(values: Sequence[str], limit: int = SUMMARY_LIMIT) -> str:
    """Join and truncate text for a history row's summary."""
    text = " ".join(v.strip() for v in values if v and v.strip())
    if len(text) > limit:
        return text[: limit - 1] + "\u2026"
    return text
