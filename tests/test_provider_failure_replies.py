"""Pin short chat replies for provider failures.

The measured defect was a phone reply containing hundreds of characters of
English provider JSON, links, a support address, and an internal request id.
These tests keep four failure classes distinct for the user while requiring
that the full redacted detail remains visible on the terminal diagnostic stream.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from urllib.error import HTTPError, URLError

import pytest

from dream.agent import OpenAIBackend

_SECRET = "sk-test-secret-that-must-not-leak"
_RATE_LIMIT_REPLY = (
    "\u0633\u0647\u0645\u06cc\u0647 \u062a\u0645\u0627\u0645 \u0634\u062f\u0647\u061b "
    "\u06cc\u06a9 \u062f\u0642\u06cc\u0642\u0647 \u062f\u06cc\u06af\u0631 "
    "\u062f\u0648\u0628\u0627\u0631\u0647 \u0628\u067e\u0631\u0633."
)
_UNREACHABLE_REPLY = (
    "\u0627\u0644\u0627\u0646 \u0628\u0647 \u0633\u0631\u0648\u06cc\u0633 "
    "\u067e\u0627\u0633\u062e\u200c\u06af\u0648\u06cc\u06cc \u0648\u0635\u0644 "
    "\u0646\u0645\u06cc\u200c\u0634\u0648\u0645\u061b \u0627\u062a\u0635\u0627\u0644 "
    "\u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646."
)
_REJECTED_REPLY = (
    "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0631\u062f \u0634\u062f\u061b "
    "\u062c\u0632\u0626\u06cc\u0627\u062a \u0631\u0627 \u062f\u0631 "
    "\u062a\u0631\u0645\u06cc\u0646\u0627\u0644 \u0628\u0628\u06cc\u0646."
)
_UNEXPECTED_REPLY = (
    "\u06cc\u06a9 \u062e\u0637\u0627\u06cc \u063a\u06cc\u0631\u0645\u0646\u062a\u0638\u0631\u0647 "
    "\u0631\u062e \u062f\u0627\u062f\u061b \u062c\u0632\u0626\u06cc\u0627\u062a "
    "\u0631\u0627 \u062f\u0631 \u062a\u0631\u0645\u06cc\u0646\u0627\u0644 "
    "\u0628\u0628\u06cc\u0646."
)


class _MalformedResponse:
    def __enter__(self) -> _MalformedResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"not-json-from-provider"


def _http_error(code: int, reason: str, body: str) -> HTTPError:
    return HTTPError(
        "https://model.test/v1/chat/completions",
        code,
        reason,
        {},
        io.BytesIO(body.encode("utf-8")),
    )


def _raise(exc: Exception) -> Callable[..., None]:
    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise exc

    return fail


def _backend_reply(monkeypatch: pytest.MonkeyPatch, urlopen: Callable[..., object]) -> str:
    monkeypatch.setenv("DREAM_MAX_RETRIES", "0")
    monkeypatch.setattr("dream.agent.urlopen", urlopen)
    backend = OpenAIBackend(model="test-model", api_key=_SECRET, base_url="https://model.test/v1")
    return str(backend.chat([{"role": "user", "content": "hello"}])["content"])


def _assert_short_persian_reply(reply: str, expected: str) -> None:
    assert reply == expected
    assert len(reply) < 90
    assert any("\u0600" <= char <= "\u06ff" for char in reply)
    assert "HTTP" not in reply
    assert "https://" not in reply
    assert "support@" not in reply
    assert "request" not in reply.lower()
    assert _SECRET not in reply


@pytest.mark.parametrize(
    ("label", "urlopen", "raw_error", "expected"),
    [
        (
            "rate_limited",
            _raise(
                _http_error(
                    429,
                    "Too Many Requests",
                    "rate limit exceeded; see https://docs.example/rate-limits; "
                    "email support@example.com; request id req_429_demo",
                )
            ),
            "HTTP 429 Too Many Requests rate limit exceeded req_429_demo",
            _RATE_LIMIT_REPLY,
        ),
        (
            "unreachable",
            _raise(URLError("connection refused by provider edge")),
            "URLError connection refused by provider edge",
            _UNREACHABLE_REPLY,
        ),
        (
            "rejected",
            _raise(
                _http_error(
                    400,
                    "Bad Request",
                    "invalid_request: tool_calls.0.function.arguments; "
                    "request id req_400_demo",
                )
            ),
            "HTTP 400 Bad Request invalid_request req_400_demo",
            _REJECTED_REPLY,
        ),
        (
            "unexpected",
            lambda *args, **kwargs: _MalformedResponse(),
            "JSONDecodeError Expecting value",
            _UNEXPECTED_REPLY,
        ),
    ],
)
def test_provider_failures_reply_shortly_and_log_redacted_detail(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    urlopen: Callable[..., object],
    raw_error: str,
    expected: str,
) -> None:
    del label
    assert _SECRET not in raw_error

    reply = _backend_reply(monkeypatch, urlopen)
    captured = capsys.readouterr()

    _assert_short_persian_reply(reply, expected)
    assert _SECRET not in captured.err
    for token in raw_error.split():
        assert token in captured.err
