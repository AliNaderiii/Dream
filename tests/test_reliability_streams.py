"""Stream stall detection: a quiet producer must not become a spinner."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge.streams import (
    StreamStalledError as BridgeStreamStalledError,
)
from dream.bridge.streams import (
    stream_text,
    stream_with_stall_guard,
)
from dream.reliability import (
    MAX_STEP_DELAY_SECONDS,
    CancelToken,
    OperationCancelled,
    StreamStalledError,
    clamp_delay,
    guarded_aiter,
    terminating_aiter,
)
from dream.reliability.deadline import clamp_delay as deadline_clamp_delay


def test_stalled_producer_raises_stream_stalled_error() -> None:
    async def never() -> object:
        await asyncio.sleep(30)
        yield "nope"

    async def _drive() -> None:
        with pytest.raises(StreamStalledError) as caught:
            async for _item in guarded_aiter(never(), stall_timeout=0.2, name="never"):
                raise AssertionError("stalled producer must not yield")
        assert caught.value.name == "never"
        assert caught.value.idle_for >= 0.2

    asyncio.run(_drive())


def test_guard_keeps_one_pending_anext() -> None:
    """A mid-stream pause shorter than the stall limit must still deliver."""

    async def burst() -> object:
        yield "a"
        await asyncio.sleep(0.15)
        yield "b"

    async def _drive() -> list[str]:
        out: list[str] = []
        async for item in guarded_aiter(burst(), stall_timeout=0.6, name="burst"):
            out.append(str(item))
        return out

    assert asyncio.run(_drive()) == ["a", "b"]


def test_heartbeat_does_not_reset_stall_clock() -> None:
    beats: list[float] = []

    async def silent() -> object:
        await asyncio.sleep(30)
        yield "nope"

    async def _drive() -> None:
        with pytest.raises(StreamStalledError):
            async for _item in guarded_aiter(
                silent(),
                stall_timeout=0.35,
                heartbeat_interval=0.08,
                emit_heartbeat=True,
                on_heartbeat=beats.append,
                name="silent",
            ):
                pass

    asyncio.run(_drive())
    assert len(beats) >= 1


def test_cancel_terminates_the_generator() -> None:
    async def slow() -> object:
        for index in range(100):
            await asyncio.sleep(0.05)
            yield index

    async def _drive() -> None:
        token = CancelToken(name="stream-stop")

        async def _cancel_soon() -> None:
            await asyncio.sleep(0.08)
            token.cancel(reason="ui-stop")

        asyncio.create_task(_cancel_soon())
        with pytest.raises(OperationCancelled):
            async for _item in guarded_aiter(
                slow(), stall_timeout=5.0, token=token, name="slow"
            ):
                pass

    asyncio.run(_drive())


def test_terminating_aiter_caps_items() -> None:
    async def many() -> object:
        for index in range(1000):
            yield index

    async def _drive() -> list[int]:
        out: list[int] = []
        async for item in terminating_aiter(many(), max_items=5, stall_timeout=2.0):
            out.append(int(item))
        return out

    assert asyncio.run(_drive()) == [0, 1, 2, 3, 4]


def test_bridge_stream_delay_is_clamped() -> None:
    assert clamp_delay(1e9) == MAX_STEP_DELAY_SECONDS
    assert deadline_clamp_delay(1e9) == MAX_STEP_DELAY_SECONDS


def test_bridge_stream_with_stall_guard_raises() -> None:
    async def never() -> object:
        await asyncio.sleep(30)
        yield {"token": "x"}

    async def _drive() -> None:
        with pytest.raises(BridgeStreamStalledError):
            async for _item in stream_with_stall_guard(
                never(), stall_timeout=0.2, name="bridge-never"
            ):
                raise AssertionError("guard must terminate")

    asyncio.run(_drive())


def test_bridge_stream_text_still_chunks() -> None:
    async def _drive() -> list[str]:
        out: list[str] = []
        async for chunk in stream_text("hello world", max_chars=12):
            out.append(chunk["token"])
        return out

    tokens = asyncio.run(_drive())
    assert "".join(tokens) == "hello world"
