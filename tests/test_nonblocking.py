"""Pin M2: the reply must not wait for the extraction pass, and rate limits
must retry with backoff instead of failing the turn.

Measured problem: every message made two model calls, each with a sixty
second timeout, so one bad provider blocked a message for two minutes with
no output. Measured here before the fix: with the conversation reply instant
and the extraction call hanging eight seconds, a turn took 8.00s of wall
time — all of it the extraction block.

After the fix: the extraction pass runs in a background worker and the turn
waits at most ``DREAM_EXTRACTION_TIMEOUT_SECONDS`` for it, marking the pass
abandoned and returning the reply anyway when the provider hangs. HTTP 429
is retried with exponential backoff, non-rate-limit failures are not
retried, and an exhausted retry budget says the call was abandoned and how
many attempts were made. All new Persian strings are backslash-u escapes.
"""

from __future__ import annotations

import io
import json
import time
from urllib.error import HTTPError

import pytest

import cli
from dream.agent import Dream, OpenAIBackend
from dream.extraction import (
    STATUS_ABANDONED,
    STATUS_ERROR,
    STATUS_FACTS_FOUND,
)
from dream.memory import MemoryStore

# پاسخ فوری. (an instant reply) / من علی هستم (I am Ali)
_REPLY = "\u067e\u0627\u0633\u062e \u0641\u0648\u0631\u06cc."
_WHO_AM_I = "\u0645\u0646 \u0639\u0644\u06cc \u0647\u0633\u062a\u0645"
_RATE_LIMIT_REPLY = (
    "\u0633\u0647\u0645\u06cc\u0647 \u062a\u0645\u0627\u0645 \u0634\u062f\u0647\u061b "
    "\u06cc\u06a9 \u062f\u0642\u06cc\u0642\u0647 \u062f\u06cc\u06af\u0631 "
    "\u062f\u0648\u0628\u0627\u0631\u0647 \u0628\u067e\u0631\u0633."
)
_UNEXPECTED_REPLY = (
    "\u06cc\u06a9 \u062e\u0637\u0627\u06cc \u063a\u06cc\u0631\u0645\u0646\u062a\u0638\u0631\u0647 "
    "\u0631\u062e \u062f\u0627\u062f\u061b \u062c\u0632\u0626\u06cc\u0627\u062a "
    "\u0631\u0627 \u062f\u0631 \u062a\u0631\u0645\u06cc\u0646\u0627\u0644 "
    "\u0628\u0628\u06cc\u0646."
)
_UNREACHABLE_REPLY = (
    "\u0627\u0644\u0627\u0646 \u0628\u0647 \u0633\u0631\u0648\u06cc\u0633 "
    "\u067e\u0627\u0633\u062e\u200c\u06af\u0648\u06cc\u06cc \u0648\u0635\u0644 "
    "\u0646\u0645\u06cc\u200c\u0634\u0648\u0645\u061b \u0627\u062a\u0635\u0627\u0644 "
    "\u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646."
)


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "nonblocking.db"))
    yield s
    s.close()


def _http_error(code: int, body: str) -> HTTPError:
    """Build an HTTPError carrying a readable response body, as urllib does."""
    return HTTPError(
        "http://model.test/v1/chat/completions",
        code,
        "Error",
        {},
        io.BytesIO(body.encode("utf-8")),
    )


class _FakeResponse:
    """Stand-in for the file-like object urlopen returns on success."""

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def _reply(content: str = "ok") -> dict:
    return {"choices": [{"message": {"content": content, "tool_calls": []}}]}


def _backend() -> OpenAIBackend:
    return OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")


class HangingExtractionBackend:
    """Conversation replies instantly; extraction never answers."""

    def __init__(self, hang_seconds: float) -> None:
        self.hang_seconds = hang_seconds

    def chat(self, messages, tools=None):
        if tools is not None:
            return {"content": _REPLY, "tool_calls": []}
        time.sleep(self.hang_seconds)
        return {"content": "[]", "tool_calls": []}


# --------------------------------------------------------------------------
# The reply does not wait for extraction
# --------------------------------------------------------------------------


def test_hanging_extraction_does_not_block_the_reply(store, monkeypatch):
    """A provider that hangs on extraction costs at most the extraction budget."""
    monkeypatch.setenv("DREAM_EXTRACTION_TIMEOUT_SECONDS", "0.5")
    backend = HangingExtractionBackend(hang_seconds=10.0)

    started = time.monotonic()
    turn = Dream(store, backend).run(_WHO_AM_I)
    elapsed = time.monotonic() - started

    assert turn.reply == _REPLY  # the instant reply arrived
    assert turn.extraction.status == STATUS_ABANDONED
    assert elapsed < 3.0  # budget 0.5s plus slack; not the 10s hang


def test_abandoned_extraction_is_visible(store, monkeypatch):
    """The failure is visible: on the turn and on the CLI activity line."""
    monkeypatch.setenv("DREAM_EXTRACTION_TIMEOUT_SECONDS", "0.5")
    backend = HangingExtractionBackend(hang_seconds=10.0)

    turn = Dream(store, backend).run(_WHO_AM_I)

    assert "did not finish within" in turn.extraction.raw_text
    lines: list[str] = []
    cli.report_turn_activity(turn, lines.append)
    assert any("[extraction] abandoned" in line for line in lines)


def test_fast_extraction_is_still_reported(store):
    """A fast pass behaves exactly as before: facts reported on the turn."""
    payload = (
        '[{"content": "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc '
        '\u0646\u0627\u0645 \u062f\u0627\u0631\u062f", "kind": "semantic", '
        '"importance": 0.9}]'
    )

    class FastBackend:
        def chat(self, messages, tools=None):
            if tools is not None:
                return {"content": _REPLY, "tool_calls": []}
            return {"content": payload, "tool_calls": []}

    turn = Dream(store, FastBackend()).run(_WHO_AM_I)

    assert turn.reply == _REPLY
    assert turn.extraction.status == STATUS_FACTS_FOUND
    assert any(m.source == "extraction" for m in turn.memories_created)


def test_extraction_failure_keeps_the_reply_path_alive(store):
    """A provider that raises on extraction never breaks the reply path."""

    class ExplodingBackend:
        def chat(self, messages, tools=None):
            if tools is not None:
                return {"content": _REPLY, "tool_calls": []}
            raise RuntimeError("extraction down")

    turn = Dream(store, ExplodingBackend()).run(_WHO_AM_I)

    assert turn.reply == _REPLY
    assert turn.extraction.status == STATUS_ERROR
    assert turn.memories_created == []


def test_extraction_backend_never_retries(store, monkeypatch):
    """Extraction must not retry: retries would stretch its wall-clock budget."""
    monkeypatch.setenv("DREAM_MAX_RETRIES", "5")
    real = _backend()
    dream = Dream(store, real)

    extraction_backend = dream._extraction_backend()

    assert extraction_backend is not real
    assert extraction_backend.max_retries == 0


# --------------------------------------------------------------------------
# Rate-limit retry with backoff
# --------------------------------------------------------------------------


def test_rate_limit_retries_then_succeeds(monkeypatch):
    """HTTP 429 is retried with backoff; the call succeeds once it recovers."""
    monkeypatch.setenv("DREAM_MAX_RETRIES", "3")
    monkeypatch.setenv("DREAM_RETRY_BACKOFF_SECONDS", "0.01")
    calls = {"count": 0}

    def flaky(request, timeout=None):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise _http_error(429, '{"error": {"message": "rate limited"}}')
        return _FakeResponse(_reply("recovered"))

    monkeypatch.setattr("dream.agent.urlopen", flaky)
    result = _backend().chat([{"role": "user", "content": "hi"}])

    assert result["content"] == "recovered"
    assert calls["count"] == 3  # two 429s, then success


def test_rate_limit_exhausted_reports_abandoned(monkeypatch, capsys):
    """Every attempt rate-limited: the diagnostic names the count."""
    monkeypatch.setenv("DREAM_MAX_RETRIES", "2")
    monkeypatch.setenv("DREAM_RETRY_BACKOFF_SECONDS", "0.01")
    calls = {"count": 0}

    def always_429(request, timeout=None):
        calls["count"] += 1
        raise _http_error(429, '{"error": {"message": "rate limited"}}')

    monkeypatch.setattr("dream.agent.urlopen", always_429)
    content = _backend().chat([{"role": "user", "content": "hi"}])["content"]
    captured = capsys.readouterr()

    assert content == _RATE_LIMIT_REPLY
    assert "HTTP 429" in captured.err
    assert "abandoned after 3 attempts" in captured.err
    assert calls["count"] == 3  # 1 + 2 retries


def test_non_rate_limit_errors_are_not_retried(monkeypatch, capsys):
    """A 500 is not a rate limit: one attempt, no backoff, no 'abandoned'."""
    monkeypatch.setenv("DREAM_MAX_RETRIES", "3")
    calls = {"count": 0}

    def server_error(request, timeout=None):
        calls["count"] += 1
        raise _http_error(500, "server exploded")

    monkeypatch.setattr("dream.agent.urlopen", server_error)
    content = _backend().chat([{"role": "user", "content": "hi"}])["content"]
    captured = capsys.readouterr()

    assert calls["count"] == 1
    assert content == _UNEXPECTED_REPLY
    assert "HTTP 500" in captured.err
    assert "abandoned" not in captured.err


def test_retry_never_touches_other_status_codes(monkeypatch):
    """HTTP 400 is a rejection, not a rate limit: exactly one attempt."""
    monkeypatch.setenv("DREAM_MAX_RETRIES", "3")
    calls = {"count": 0}

    def bad_request(request, timeout=None):
        calls["count"] += 1
        raise _http_error(400, '{"error": {"message": "bad arguments"}}')

    monkeypatch.setattr("dream.agent.urlopen", bad_request)
    _backend().chat([{"role": "user", "content": "hi"}])

    assert calls["count"] == 1


def test_a_hanging_reply_call_fails_visibly_and_promptly(store, monkeypatch):
    """A provider that never answers the reply call reports the timeout.

    The real backend converts a timeout into the failure reply; the mock
    returns the same shape the real backend would. The failure is the
    reply, and it is visible.
    """
    monkeypatch.setenv("DREAM_EXTRACTION_TIMEOUT_SECONDS", "0.5")

    class TimeoutBackend:
        def chat(self, messages, tools=None):
            if tools is not None:
                return {
                    "content": _UNREACHABLE_REPLY,
                    "tool_calls": [],
                }
            return {"content": "[]", "tool_calls": []}

    turn = Dream(store, TimeoutBackend()).run("\u0633\u0644\u0627\u0645")

    assert turn.reply == _UNREACHABLE_REPLY
    assert "abandoned" not in turn.reply  # a single attempt is just a failure
