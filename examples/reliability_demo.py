#!/usr/bin/env python3
"""Offline demo of the reliability toolkit.

Shows cancellation, deadlines, the watchdog, budgets (EN+FA), backpressure,
stream stall detection, SQLite helpers, and the degradation ladder. No
network, no provider, no hang.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dream.agentmodes.cancel import CancellationToken  # noqa: E402
from dream.reliability import (  # noqa: E402
    BoundedBuffer,
    Budget,
    BudgetExceeded,
    BudgetKind,
    Deadline,
    DeadlineExceeded,
    Degradation,
    OverflowPolicy,
    ResourceSupervisor,
    StreamStalledError,
    Watchdog,
    adapt_agentmodes,
    clamp_delay,
    durable_write,
    guarded_aiter,
)
from dream.reliability.db import (  # noqa: E402
    claim_delivery,
    connect_sqlite,
    ensure_delivery_schema,
    increment_counter,
    read_counter,
)


def demo_cancel() -> None:
    print("=== cancel ===")
    p4 = CancellationToken()
    token = adapt_agentmodes(p4, name="demo")
    p4.cancel()
    print("adapted P4 token cancelled", token.is_cancelled(), token.snapshot()["reason"])


def demo_deadline_and_watchdog() -> None:
    print("=== deadline / watchdog ===")
    print("clamped client delay", clamp_delay(1e9))

    def hang() -> None:
        time.sleep(30)

    deadline = Deadline.after(0.2, owner="demo", step="hang")
    watchdog = Watchdog(deadline)
    try:
        watchdog.run(hang)
        print("watchdog missed")
    except DeadlineExceeded as exc:
        print("reaped", watchdog.reaped, "cause", watchdog.cause)
        print("owner", exc.owner, "step", exc.step)


def demo_budget() -> None:
    print("=== budget ===")
    budget = Budget(tokens=2, owner="demo", step="reply")
    budget.consume(BudgetKind.TOKENS, 2)
    try:
        budget.consume(BudgetKind.TOKENS, 1)
    except BudgetExceeded as exc:
        print(exc.bilingual())


def demo_backpressure() -> None:
    print("=== backpressure ===")
    buf = BoundedBuffer(maxlen=3, policy=OverflowPolicy.DROP_OLDEST)
    for item in range(6):
        buf.put({"n": item})
    print("bounded", buf.snapshot(), "dropped", buf.dropped)


def demo_stream() -> None:
    print("=== stream stall ===")

    async def silent() -> object:
        await asyncio.sleep(10)
        yield "never"

    async def _drive() -> None:
        try:
            async for _item in guarded_aiter(silent(), stall_timeout=0.2, name="demo"):
                print("yielded", _item)
        except StreamStalledError as exc:
            print("stalled", exc.name, f"idle={exc.idle_for:.2f}s")

    asyncio.run(_drive())


def demo_db(tmp: Path) -> None:
    print("=== sqlite helpers ===")
    db = tmp / "demo.db"
    conn = connect_sqlite(db)
    increment_counter(conn, amount=3)
    print("counter", read_counter(conn))
    ensure_delivery_schema(conn)
    first = claim_delivery(conn, reminder_id=1, destination="terminal", fired_at=1.0)
    second = claim_delivery(conn, reminder_id=1, destination="terminal", fired_at=1.0)
    print("claim first", first, "claim again", second)
    conn.close()
    durable_write(tmp / "note.txt", "ok")
    print("durable", (tmp / "note.txt").read_text(encoding="utf-8"))


def demo_supervisor() -> None:
    print("=== supervisor ===")
    hold = threading.Event()

    def idle() -> None:
        hold.wait(timeout=5)

    with ResourceSupervisor(idle_timeout=0.2, max_restarts=0) as sup:
        sup.spawn_thread("idle", idle)
        time.sleep(0.3)
        print("reaped", sup.reap_stale())
    hold.set()


def demo_degrade() -> None:
    print("=== degrade ladder ===")
    ladder = Degradation()
    ladder.step_down("provider timeout")
    ladder.step_down("still failing")
    print(ladder.bilingual())


def main() -> int:
    print("reliability demo")
    demo_cancel()
    demo_deadline_and_watchdog()
    demo_budget()
    demo_backpressure()
    demo_stream()
    with tempfile.TemporaryDirectory() as tmp:
        demo_db(Path(tmp))
    demo_supervisor()
    demo_degrade()
    print("demo done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
