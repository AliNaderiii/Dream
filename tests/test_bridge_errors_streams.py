"""Unit tests for the bridge error taxonomy and streaming helpers."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge import errors as E
from dream.bridge.streams import (
    DEFAULT_MAX_CHARS,
    Stream,
    ensure_awaitable,
    is_async_generator,
    stream_chunks,
    stream_text,
    tokenise,
)

# --------------------------------------------------------------------------- #
# Error taxonomy.
# --------------------------------------------------------------------------- #


def test_code_table_covers_every_documented_code():
    expected = {
        E.PARSE_ERROR,
        E.INVALID_REQUEST,
        E.METHOD_NOT_FOUND,
        E.INVALID_PARAMS,
        E.INTERNAL_ERROR,
        E.PROVIDER_ERROR,
        E.AUTH_ERROR,
        E.RATE_LIMITED,
        E.CONTEXT_OVERFLOW,
        E.APPROVAL_REQUIRED,
        E.TOOL_ERROR,
        E.RESOURCE_EXHAUSTED,
    }
    assert expected.issubset(set(E.ERRORS))


def test_bridge_error_carries_code_and_data():
    err = E.BridgeError(E.INVALID_PARAMS, "bad", data={"field": "x"})
    assert err.code == E.INVALID_PARAMS
    assert err.data == {"field": "x"}


def test_invalid_params_helper_builds_error():
    err = E.invalid_params("missing x")
    assert err.code == E.INVALID_PARAMS
    assert str(err) == "missing x"


def test_serialise_error_maps_value_error_to_invalid_params():
    out = E.serialise_error(ValueError("nope"))
    assert out["error"]["code"] == E.INVALID_PARAMS
    assert out["error"]["message"] == "nope"
    assert out["id"] is None
    assert "data" not in out["error"]  # prod mode: no traceback


def test_serialise_error_redacts_bearer_tokens(monkeypatch):
    monkeypatch.setenv("DREAM_DEV", "1")
    out = E.serialise_error(ValueError("Authorization: Bearer sk-secret-123456"))
    msg = out["error"]["message"]
    assert "sk-secret-123456" not in msg
    assert "***" in msg


def test_serialise_error_includes_traceback_in_dev_mode(monkeypatch):
    monkeypatch.setenv("DREAM_DEV", "1")
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        out = E.serialise_error(exc, request_id=7)
    assert out["id"] == 7
    assert out["error"]["data"]["type"] == "RuntimeError"
    assert "RuntimeError: boom" in out["error"]["data"]["traceback"]


def test_rate_limit_and_context_and_auth_classification():
    assert (
        E.serialise_error(Exception("HTTP 429 too many requests"))["error"]["code"]
        == E.RATE_LIMITED
    )
    assert (
        E.serialise_error(Exception("context length exceeded"))["error"]["code"]
        == E.CONTEXT_OVERFLOW
    )
    assert E.serialise_error(Exception("401 Unauthorized"))["error"]["code"] == E.AUTH_ERROR


def test_unknown_exception_falls_back_to_internal():
    out = E.serialise_error(RuntimeError("unexpected"))
    assert out["error"]["code"] == E.INTERNAL_ERROR
    assert "RuntimeError" in out["error"]["message"]


def test_error_from_code_is_self_contained():
    out = E.error_from_code(E.METHOD_NOT_FOUND, request_id="abc", method="bogus")
    assert out["id"] == "abc"
    assert out["error"]["code"] == E.METHOD_NOT_FOUND
    assert out["error"]["data"] == {"method": "bogus"}


def test_bridge_error_passes_through_its_chosen_code():
    err = E.BridgeError(E.APPROVAL_REQUIRED, "needs approval", data={"approval_id": "x"})
    out = E.serialise_error(err, request_id=3)
    assert out["error"]["code"] == E.APPROVAL_REQUIRED
    assert out["error"]["data"]["approval_id"] == "x"


# --------------------------------------------------------------------------- #
# Streaming helpers.
# --------------------------------------------------------------------------- #


def test_tokenise_word_boundaries_and_hard_split():
    assert tokenise("hello world") == ["hello ", "world"]
    assert tokenise("سلام دنیا") == ["سلام ", "دنیا"]
    # An over-long run with no whitespace is hard-split at the cap.
    long = "x" * (DEFAULT_MAX_CHARS * 3)
    pieces = tokenise(long)
    assert len(pieces) == 3
    assert "".join(pieces) == long
    assert tokenise("") == []


def test_tokenise_preserves_text_on_rejoin():
    for text in ("", "a", "one two three", "  spaced  out  ", "فارسی و English mixed"):
        assert "".join(tokenise(text)) == text


def test_is_async_generator_detects_async_gen():
    async def gen():
        yield 1

    assert is_async_generator(gen()) is True
    assert is_async_generator(42) is False


def test_stream_text_yields_token_chunks():
    async def main():
        return [c async for c in stream_text("hi there")]

    chunks = asyncio.run(main())
    assert chunks == [{"token": "hi "}, {"token": "there"}]


def test_stream_chunks_returns_stream_with_final():
    def produce():
        return {"reply": "hello mars", "extra": 1}

    async def main():
        stream = await stream_chunks(produce, to_text=lambda r: r["reply"])
        chunks = [c async for c in stream.chunks]
        return stream, chunks

    stream, chunks = asyncio.run(main())
    assert isinstance(stream, Stream)
    assert stream.final == {"reply": "hello mars", "extra": 1}
    assert "".join(c["token"] for c in chunks) == "hello mars"


def test_ensure_awaitable_wraps_plain_value():
    async def main():
        value = await ensure_awaitable(42)
        assert value == 42

    asyncio.run(main())


def test_ensure_awaitable_passes_through_real_coroutine():
    async def coro():
        return "ok"

    async def main():
        assert await ensure_awaitable(coro()) == "ok"

    asyncio.run(main())


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
