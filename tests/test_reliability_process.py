"""Real-process and real-thread proofs for cancellation, watchdog, leaks."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from dream.reliability import (
    CancelToken,
    Deadline,
    DeadlineExceeded,
    OperationCancelled,
    ResourceSupervisor,
    Watchdog,
)
from dream.reliability.deadline import MAX_DEADLINE_SECONDS


def test_cancel_real_subprocess_within_deadline() -> None:
    token = CancelToken(name="proc")
    deadline = Deadline.after(3.0, owner="test", step="sleep")
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    token.link_subprocess(proc)
    started = time.monotonic()
    time.sleep(0.15)
    token.cancel(reason="test-stop")
    proc.wait(timeout=2.0)
    elapsed = time.monotonic() - started
    assert proc.poll() is not None
    assert token.is_cancelled() is True
    assert elapsed < deadline.remaining() + 3.0
    assert elapsed < 5.0


def test_cancel_async_operation_within_deadline() -> None:
    import asyncio

    async def _work(token: CancelToken) -> None:
        for _ in range(200):
            token.throw_if_cancelled()
            await asyncio.sleep(0.02)

    async def _drive() -> None:
        token = CancelToken(name="async")
        task = asyncio.create_task(_work(token))
        await asyncio.sleep(0.08)
        token.cancel(reason="async-stop")
        with pytest.raises(OperationCancelled) as caught:
            await task
        assert caught.value.reason == "async-stop"

    asyncio.run(_drive())


def test_watchdog_reaps_hung_thread_and_records_cause() -> None:
    clock = time.monotonic()

    def hang() -> str:
        time.sleep(45)
        return "never"

    deadline = Deadline.after(0.2, owner="engine", step="model-call")
    watchdog = Watchdog(deadline)
    with pytest.raises(DeadlineExceeded) as caught:
        watchdog.run(hang)
    elapsed = time.monotonic() - clock
    assert watchdog.reaped is True
    assert watchdog.cause is not None
    assert "model-call" in watchdog.cause
    assert caught.value.owner == "engine"
    assert caught.value.step == "model-call"
    assert elapsed < 2.0


def test_watchdog_async_reaps_hung_coroutine() -> None:
    import asyncio

    async def hang() -> None:
        await asyncio.sleep(45)

    async def _drive() -> None:
        deadline = Deadline.after(0.15, owner="engine", step="async-hang")
        watchdog = Watchdog(deadline)
        with pytest.raises(DeadlineExceeded) as caught:
            await watchdog.run_async(hang())
        assert watchdog.reaped is True
        assert caught.value.step == "async-hang"

    asyncio.run(_drive())


def test_supervisor_reaps_stale_thread() -> None:
    import threading

    hold = threading.Event()

    def idle() -> None:
        hold.wait(timeout=30)

    with ResourceSupervisor(idle_timeout=0.15, max_restarts=0, sleep=lambda _s: None) as sup:
        worker = sup.spawn_thread("idle-one", idle)
        time.sleep(0.25)
        reaped = sup.reap_stale()
        assert "idle-one" in reaped
        assert worker.status.value == "reaped"
    hold.set()


def test_supervisor_restarts_with_sidecar_budget() -> None:
    sleeps: list[float] = []

    def boom() -> None:
        raise RuntimeError("die")

    with ResourceSupervisor(
        idle_timeout=5.0,
        backoff=(0.01, 0.02, 0.03),
        max_restarts=3,
        sleep=sleeps.append,
    ) as sup:
        worker = sup.spawn_thread("flaky", boom)
        time.sleep(0.05)
        assert worker.is_alive() is False
        assert sup.restart("flaky") is True
        time.sleep(0.05)
        assert worker.restarts == 1
        assert sup.restart("flaky") is True
        time.sleep(0.05)
        assert sup.restart("flaky") is True
        time.sleep(0.05)
        assert worker.restarts == 3
        assert sup.restart("flaky") is False
        assert worker.status.value == "failed"
    assert sleeps == [0.01, 0.02, 0.03]


def test_supervisor_process_shutdown_does_not_leak() -> None:
    with ResourceSupervisor(idle_timeout=5.0) as sup:
        worker = sup.spawn_process(
            "sleeper",
            [sys.executable, "-c", "import time; time.sleep(30)"],
        )
        assert worker.is_alive() is True
        pid = worker.proc.pid if worker.proc is not None else None
        assert pid is not None
    # Context exit must terminate the child.
    assert worker.proc is not None
    assert worker.proc.poll() is not None


def test_async_and_subprocess_cancel_together() -> None:
    """DoD: one token cancels a live async wait *and* a real child process."""
    import asyncio

    token = CancelToken(name="both")
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    token.link_subprocess(proc)

    async def _drive() -> None:
        async def _spin() -> None:
            while True:
                token.throw_if_cancelled()
                await asyncio.sleep(0.03)

        task = asyncio.create_task(_spin())
        await asyncio.sleep(0.1)
        token.cancel(reason="both-stop")
        with pytest.raises(OperationCancelled):
            await task
        proc.wait(timeout=2.0)

    asyncio.run(_drive())
    assert proc.poll() is not None
    assert token.is_cancelled() is True


def test_far_future_deadline_cannot_be_unbounded() -> None:
    deadline = Deadline.after(1e9, owner="cap", step="wait")
    assert deadline.remaining() <= MAX_DEADLINE_SECONDS + 0.05
