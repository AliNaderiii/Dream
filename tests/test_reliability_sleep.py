"""Deterministic tests for cooperative interruptible sleep helpers (SEC-06)."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from dream.agent import OpenAIBackend
from dream.reliability.cancel import CancelToken, OperationCancelled
from dream.reliability.sleep import ainterruptible_sleep, interruptible_sleep

_LOOSE_BOUND = 0.6
_SNIP_BOUND = 0.25


def _elapsed(started: float) -> float:
    return time.monotonic() - started


# --------------------------------------------------------------------------- #
# Synchronous helper.
# --------------------------------------------------------------------------- #


def test_zero_and_negative_duration_return_promptly() -> None:
    for duration in (0.0, -0.01, -5.0):
        started = time.monotonic()
        interruptible_sleep(duration)
        assert _elapsed(started) < _LOOSE_BOUND


def test_cancellation_before_sleep_starts_is_observed() -> None:
    token = CancelToken(name="pre-cancelled")
    token.cancel(reason="stop")
    started = time.monotonic()
    with pytest.raises(OperationCancelled) as caught:
        interruptible_sleep(10.0, token, granularity=0.01)
    assert caught.value.reason == "stop"
    assert _elapsed(started) < _SNIP_BOUND


def test_sync_sleep_completes_near_requested_duration() -> None:
    started = time.monotonic()
    interruptible_sleep(0.03, granularity=0.01)
    elapsed = _elapsed(started)
    assert elapsed >= 0.01
    assert elapsed < _LOOSE_BOUND


def test_sync_cancellation_interrupts_within_granularity() -> None:
    token = CancelToken(name="sync-cancel")
    fired = threading.Event()

    def wait_for_cancel() -> None:
        try:
            interruptible_sleep(2.0, token, granularity=0.005)
        except OperationCancelled:
            fired.set()

    started = time.monotonic()
    worker = threading.Thread(target=wait_for_cancel, daemon=True)
    worker.start()
    time.sleep(0.02)
    token.cancel(reason="sync-stop")
    worker.join(timeout=0.5)
    assert not worker.is_alive()
    assert fired.is_set()
    assert _elapsed(started) < _SNIP_BOUND


def test_sync_helper_uses_token_event_not_time_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    token = CancelToken(name="no-spin")
    monkeypatch.setattr(
        "dream.reliability.sleep.time.sleep",
        lambda _seconds: pytest.fail("time.sleep must not run with a cancellation token"),
    )
    interruptible_sleep(0.01, token, granularity=0.005)
    assert not token.is_cancelled()


def test_invalid_granularity_is_rejected() -> None:
    for granularity in (-0.01, 0.0, float("nan")):
        with pytest.raises(ValueError, match="granularity"):
            interruptible_sleep(0.01, granularity=granularity)


# --------------------------------------------------------------------------- #
# Asynchronous helper.
# --------------------------------------------------------------------------- #


def test_async_zero_and_negative_duration_return_promptly() -> None:
    async def scenario() -> None:
        started = time.monotonic()
        for duration in (0.0, -1.0):
            await ainterruptible_sleep(duration)
        assert _elapsed(started) < _LOOSE_BOUND

    asyncio.run(scenario())


def test_async_sleep_completes_near_requested_duration() -> None:
    async def scenario() -> None:
        started = time.monotonic()
        await ainterruptible_sleep(0.03, granularity=0.01)
        assert _elapsed(started) >= 0.01
        assert _elapsed(started) < _LOOSE_BOUND

    asyncio.run(scenario())


def test_async_cancellation_interrupts_without_blocking_loop() -> None:
    async def scenario() -> None:
        token = CancelToken(name="async-cancel")
        started = time.monotonic()
        task = asyncio.create_task(
            ainterruptible_sleep(2.0, token, granularity=0.005),
            name="interruptible-sleep",
        )
        await asyncio.sleep(0.02)
        token.cancel(reason="async-stop")
        with pytest.raises(OperationCancelled) as caught:
            await asyncio.wait_for(task, timeout=0.5)
        assert caught.value.reason == "async-stop"
        assert _elapsed(started) < _SNIP_BOUND

    asyncio.run(scenario())


def test_async_cancellation_before_start_is_observed() -> None:
    async def scenario() -> None:
        token = CancelToken(name="async-pre")
        token.cancel()
        with pytest.raises(OperationCancelled):
            await ainterruptible_sleep(10.0, token)

    asyncio.run(scenario())


def test_async_invalid_granularity_is_rejected() -> None:
    async def scenario() -> None:
        with pytest.raises(ValueError, match="granularity"):
            await ainterruptible_sleep(0.01, granularity=0.0)

    asyncio.run(scenario())


def test_asyncio_cancelled_error_propagates() -> None:
    async def scenario() -> None:
        task = asyncio.create_task(ainterruptible_sleep(10.0), name="cancelled-sleep")
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_async_token_from_asyncio_event_observes_stop() -> None:
    async def scenario() -> None:
        stop = asyncio.Event()
        token = CancelToken.from_async_event(stop, name="async-event-stop")
        task = asyncio.create_task(
            ainterruptible_sleep(2.0, token, granularity=0.005),
            name="async-event-sleep",
        )
        await asyncio.sleep(0.02)
        stop.set()
        with pytest.raises(OperationCancelled):
            await asyncio.wait_for(task, timeout=0.5)
        assert token.is_cancelled()
        assert stop.is_set()

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Existing callers and scope hygiene.
# --------------------------------------------------------------------------- #


def test_agent_retry_backoff_durations_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = OpenAIBackend(api_key="test-key", base_url="https://example.invalid")
    sleeps: list[float] = []

    def record(
        seconds: float,
        cancel: CancelToken | None = None,
        granularity: float = 0.05,
    ) -> None:
        assert cancel is None
        assert granularity == 0.05
        sleeps.append(seconds)

    monkeypatch.setattr("dream.agent.interruptible_sleep", record)
    monkeypatch.setattr(
        backend,
        "_attempt_chat",
        lambda _messages, _tools=None: (429, {"error": "rate limited"}),
    )

    backend.chat([], max_retries=2)

    base = backend.retry_backoff_seconds
    assert sleeps == [base, base * 2.0]


def test_scoped_production_sleeps_use_the_helper() -> None:
    root = Path(__file__).resolve().parent.parent
    scoped = [
        root / "dream" / "agent.py",
        root / "dream" / "telegram.py",
        root / "dream" / "acp" / "client.py",
        root / "dream" / "bridge" / "methods.py",
        root / "dream" / "bridge" / "methods_research.py",
        *list((root / "dream" / "connectivity" / "adapters").glob("*.py")),
    ]
    for path in scoped:
        text = path.read_text(encoding="utf-8")
        assert "time.sleep(" not in text, f"{path} still calls time.sleep"
        assert "asyncio.sleep(" not in text, f"{path} still calls asyncio.sleep"
