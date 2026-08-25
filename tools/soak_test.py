#!/usr/bin/env python3
"""Bounded soak for the reliability toolkit.

Exercises cancel, watchdog, budgets, backpressure, stalling streams,
SQLite helpers, and the supervisor in a loop. Always self-terminates:
a 30-second wall-clock cap via ``SIGALRM`` plus a monotonic check.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dream.reliability import (  # noqa: E402
    BoundedBuffer,
    Budget,
    BudgetExceeded,
    BudgetKind,
    CancelToken,
    Deadline,
    DeadlineExceeded,
    Degradation,
    OverflowPolicy,
    ResourceSupervisor,
    StreamStalledError,
    Watchdog,
    durable_write,
    guarded_aiter,
)
from dream.reliability.db import (  # noqa: E402
    claim_delivery,
    connect_sqlite,
    ensure_delivery_schema,
    increment_counter,
)

WALL_CAP = 30.0
SOFT_CAP = 25.0


def _hard_stop(_signum: int, _frame: object) -> None:
    print("SOAK WALL-CLOCK CAP REACHED", file=sys.stderr)
    raise SystemExit(2)


def _cancel_round() -> None:
    token = CancelToken(name="soak")
    child = token.child("step")
    token.cancel(reason="soak")
    child.throw_if_cancelled()


def _watchdog_round() -> None:
    def hang() -> None:
        time.sleep(8)

    deadline = Deadline.after(0.12, owner="soak", step="hang")
    Watchdog(deadline).run(hang)


def _budget_round() -> None:
    budget = Budget(tokens=1, owner="soak", step="turn")
    budget.consume(BudgetKind.TOKENS, 1)
    budget.consume(BudgetKind.TOKENS, 1)


def _buffer_round() -> None:
    buf = BoundedBuffer(maxlen=8, policy=OverflowPolicy.DROP_OLDEST)
    for item in range(32):
        buf.put(item)
    if len(buf) > 8:
        raise RuntimeError("buffer grew past maxlen")


async def _stream_round() -> None:
    async def silent() -> object:
        await asyncio.sleep(8)
        yield "x"

    async for _item in guarded_aiter(silent(), stall_timeout=0.12, name="soak"):
        pass


def _db_round(tmp: Path, index: int) -> None:
    db = tmp / "soak.db"
    conn = connect_sqlite(db)
    increment_counter(conn, amount=1)
    ensure_delivery_schema(conn)
    claim_delivery(
        conn, reminder_id=index, destination="terminal", fired_at=float(index)
    )
    conn.close()
    durable_write(tmp / "mark.txt", str(index))


def _supervisor_round() -> None:
    with ResourceSupervisor(idle_timeout=0.1, max_restarts=0, sleep=lambda _s: None) as sup:
        sup.spawn_thread("noop", lambda: None)
        time.sleep(0.15)
        sup.reap_stale()


def main() -> int:
    started = time.monotonic()
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _hard_stop)
        signal.alarm(int(WALL_CAP))

    rounds = 0
    expected = {
        "cancel": 0,
        "watchdog": 0,
        "budget": 0,
        "buffer": 0,
        "stream": 0,
        "db": 0,
        "supervisor": 0,
    }
    ladder = Degradation()

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        while time.monotonic() - started < SOFT_CAP:
            try:
                _cancel_round()
            except Exception:
                expected["cancel"] += 1
            try:
                _watchdog_round()
            except DeadlineExceeded:
                expected["watchdog"] += 1
            try:
                _budget_round()
            except BudgetExceeded:
                expected["budget"] += 1
            _buffer_round()
            expected["buffer"] += 1
            try:
                asyncio.run(_stream_round())
            except StreamStalledError:
                expected["stream"] += 1
            _db_round(tmp, rounds)
            expected["db"] += 1
            _supervisor_round()
            expected["supervisor"] += 1
            rounds += 1
            if rounds == 1:
                ladder.step_down("soak start")

    elapsed = time.monotonic() - started
    missing = [name for name, count in expected.items() if count == 0]
    print(
        f"SOAK PASS rounds={rounds} elapsed={elapsed:.2f}s "
        f"counts={expected} ladder={ladder.level.value}"
    )
    if missing:
        print("SOAK FAIL missing", missing, file=sys.stderr)
        return 1
    if elapsed >= WALL_CAP:
        print("SOAK FAIL exceeded wall cap", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
