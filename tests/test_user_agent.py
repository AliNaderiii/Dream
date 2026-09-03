"""User-Agent hardening (SEC-07).

Dream identifies itself to model providers with one ``User-Agent`` header,
overridable through ``DREAM_USER_AGENT`` for owners behind unusual filters.
Two defects motivated this module:

- the default was pinned to an obsolete ``0.1.0`` while the package shipped
  as ``0.4.6``, so provider logs misreported every Dream release;
- the override only refused bare CR/LF. ``http.client`` still accepts a
  line break that is followed by a space or TAB as obsolete header folding,
  and NUL, DEL and the other controls passed straight through, so a hostile
  or mangled environment value could still reach the request line.

The policy pinned here: ``None``/empty use the versioned default silently;
surrounding spaces and TABs are trimmed; any remaining C0/C1 control, DEL,
whitespace-only, over-long (200+), or non-ISO-8859-1 value is rejected with a
bounded warning that never echoes the value; every other value is forwarded
exactly. No test here opens a socket.
"""

from __future__ import annotations

import http.client
import json
import logging
import re
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPHandler, Request, build_opener

import pytest

import dream
from dream.agent import (
    DEFAULT_USER_AGENT,
    USER_AGENT_MAX_LENGTH,
    USER_AGENT_PRODUCT,
    OpenAIBackend,
    _resolve_user_agent,
)

_ROOT = Path(__file__).resolve().parent.parent
_VERSION = "9.9.9-test"
_DEFAULT = f"{USER_AGENT_PRODUCT}/{_VERSION}"
_LOGGER = "dream.agent"

# Strings that must never reach a log record: a credential-looking override
# and a URL that carries a key, the two things an owner is most likely to
# paste into the wrong variable.
_SECRET = "sk-live-ua-must-not-leak-a1b2c3d4"
_KEYED_URL = "https://model.test/v1?key=very-private-value"


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == _LOGGER]


def _stdlib_accepts_header_value(value: str) -> bool:
    """True when ``http.client`` would put ``value`` on the wire unchanged.

    ``putheader`` only appends to the connection's buffer; nothing is sent
    and no socket is opened.
    """
    connection = http.client.HTTPConnection("model.test")
    connection.putrequest("POST", "/", skip_host=True, skip_accept_encoding=True)
    try:
        connection.putheader("User-Agent", value)
    except ValueError:
        return False
    finally:
        connection.close()
    return True


def _joined(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in _records(caplog))


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------


def test_none_uses_the_versioned_default() -> None:
    assert _resolve_user_agent(None, _VERSION) == _DEFAULT


def test_empty_string_uses_the_versioned_default() -> None:
    assert _resolve_user_agent("", _VERSION) == _DEFAULT


@pytest.mark.parametrize("raw", ["   ", "\t", " \t ", "\t\t"])
def test_whitespace_only_uses_the_versioned_default(raw: str) -> None:
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT


def test_unconfigured_values_do_not_log(caplog: pytest.LogCaptureFixture) -> None:
    # "Not set" is the normal case and must stay quiet at WARNING.
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    _resolve_user_agent(None, _VERSION)
    _resolve_user_agent("", _VERSION)
    assert _records(caplog) == []


def test_whitespace_only_is_logged_as_blank(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    _resolve_user_agent("   ", _VERSION)
    (record,) = _records(caplog)
    assert record.levelno == logging.WARNING
    assert record.__dict__["user_agent_reason"] == "blank"
    assert record.__dict__["user_agent_length"] == 3


def test_default_is_a_product_token_of_the_given_version() -> None:
    value = _resolve_user_agent(None, _VERSION)
    product, _, version = value.partition("/")
    assert product == USER_AGENT_PRODUCT == "dream-assistant"
    assert version == _VERSION


def test_default_never_contains_line_breaks_or_controls() -> None:
    assert re.search(r"[\x00-\x1f\x7f-\x9f]", DEFAULT_USER_AGENT) is None
    assert re.search(r"[\x00-\x1f\x7f-\x9f]", _resolve_user_agent(None, _VERSION)) is None


# --------------------------------------------------------------------------
# Valid custom values
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "custom-agent/1.0",
        "Mozilla/5.0 (compatible; MyProxy/2.1; +https://example.test/bot)",
        "dream-assistant/0.4.6 (owner build; linux)",
        "a",
        "x" * USER_AGENT_MAX_LENGTH,
        "Caf\u00e9-Agent/1.0",  # printable ISO-8859-1 stays forwardable, as before
    ],
)
def test_valid_custom_values_are_preserved_exactly(
    raw: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    assert _resolve_user_agent(raw, _VERSION) == raw
    assert _records(caplog) == [], "an accepted override is not worth a log line"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  custom-agent/1.0  ", "custom-agent/1.0"),
        ("custom-agent/1.0 ", "custom-agent/1.0"),
        (" custom-agent/1.0", "custom-agent/1.0"),
        ("\tcustom-agent/1.0\t", "custom-agent/1.0"),
        (" \t custom-agent/1.0 \t ", "custom-agent/1.0"),
    ],
)
def test_surrounding_spaces_and_tabs_are_trimmed(raw: str, expected: str) -> None:
    # Surrounding spaces and TABs (the optional whitespace HTTP ignores around
    # a field value) are removed, matching the old ``strip()`` for the values
    # that used to be accepted. The interior is never touched.
    assert _resolve_user_agent(raw, _VERSION) == expected


@pytest.mark.parametrize(
    "raw",
    ["custom-agent/1.0\n", "\r\ncustom-agent/1.0\r\n", "\x0bcustom-agent/1.0", "\x85custom/1"],
)
def test_surrounding_controls_are_not_silently_trimmed(raw: str) -> None:
    # Only SP/HTAB padding is dropped. A line ending or other control at the
    # edge is a rejection like anywhere else, so nothing control-shaped is
    # ever discarded on the way to the wire. (The old ``strip()`` silently
    # ate a trailing newline; this is the one deliberate policy change.)
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT


def test_interior_spaces_are_kept_verbatim() -> None:
    raw = "custom-agent/1.0   (two   gaps)"
    assert _resolve_user_agent(raw, _VERSION) == raw


def test_exactly_the_maximum_length_is_accepted() -> None:
    raw = "a" * USER_AGENT_MAX_LENGTH
    assert _resolve_user_agent(raw, _VERSION) == raw


def test_padding_does_not_count_towards_the_length_limit() -> None:
    # The limit applies to what would be sent, not to the raw padding.
    raw = "  " + "a" * USER_AGENT_MAX_LENGTH + "  "
    assert _resolve_user_agent(raw, _VERSION) == "a" * USER_AGENT_MAX_LENGTH


# --------------------------------------------------------------------------
# Header injection
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "custom/1.0\nX-Injected: 1",
        "custom/1.0\r\nX-Injected: 1",
        "custom/1.0\r\nX-Injected: 1\r\n\r\nGET /smuggled HTTP/1.1",
        "\ncustom/1.0",
        "custom/1.0\nmore",
    ],
)
def test_newline_injection_is_rejected(raw: str) -> None:
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT


@pytest.mark.parametrize("raw", ["custom/1.0\rX-Injected: 1", "\rcustom/1.0", "a\rb"])
def test_carriage_return_injection_is_rejected(raw: str) -> None:
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT


@pytest.mark.parametrize(
    "raw",
    [
        "custom/1.0\r\n X-Folded: 1",
        "custom/1.0\r\n\tX-Folded: 1",
        "custom/1.0\n X-Folded: 1",
        "custom/1.0\n\tX-Folded: 1",
    ],
)
def test_obsolete_line_folding_is_rejected(raw: str) -> None:
    # ``http.client`` accepts a line break followed by SP/HTAB as obsolete
    # folding, so filtering bare CR/LF alone would let these through. Prove
    # the stdlib would have accepted them, then prove Dream refuses them.
    assert _stdlib_accepts_header_value(raw), "stdlib tolerance changed; revisit the policy"
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT


def test_newline_injection_is_logged_without_the_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    raw = f"{_SECRET}\r\nX-Injected: {_KEYED_URL}"
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT
    (record,) = _records(caplog)
    assert record.levelno == logging.WARNING
    assert record.__dict__["user_agent_reason"] == "control_character"
    assert record.__dict__["user_agent_length"] == len(raw)
    message = record.getMessage()
    assert "control_character" in message
    assert str(len(raw)) in message
    assert _SECRET not in message
    assert "very-private-value" not in message
    assert "X-Injected" not in message
    assert "\r" not in message and "\n" not in message


# --------------------------------------------------------------------------
# Control characters
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "control",
    [chr(code) for code in range(0x00, 0x20) if chr(code) not in "\t\n\r"]
    + ["\x7f"]
    + [chr(code) for code in range(0x80, 0xA0)],
)
def test_every_other_control_character_is_rejected(control: str) -> None:
    # NUL, the remaining C0 controls, DEL and the C1 range: a NUL truncates
    # in C-based proxies, ESC drives terminals reading a log, NEL (0x85) is
    # a line break to some parsers. None of them belong in a product token.
    assert _resolve_user_agent(f"custom{control}/1.0", _VERSION) == _DEFAULT
    assert _resolve_user_agent(f"{control}custom/1.0", _VERSION) == _DEFAULT
    assert _resolve_user_agent(f"custom/1.0{control}", _VERSION) == _DEFAULT


def test_null_byte_is_rejected_and_logged_safely(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    raw = f"custom/1.0\x00{_SECRET}"
    # The stdlib would happily send the NUL; Dream must not rely on it.
    assert _stdlib_accepts_header_value(raw)
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT
    (record,) = _records(caplog)
    assert record.__dict__["user_agent_reason"] == "control_character"
    assert "\x00" not in record.getMessage()
    assert _SECRET not in record.getMessage()


def test_interior_tab_is_rejected() -> None:
    # Policy: TAB is trimmed at the ends (surrounding whitespace) but refused
    # inside the value, where it is the folding whitespace a split needs.
    assert _resolve_user_agent("custom\t/1.0", _VERSION) == _DEFAULT
    assert _resolve_user_agent("custom/1.0\tX-Injected: 1", _VERSION) == _DEFAULT


def test_tab_can_never_introduce_a_second_header_line() -> None:
    # Whatever TAB combination is supplied, the resolved value is a single
    # line with no folding whitespace left in it.
    for raw in ("\tcustom/1.0", "custom/1.0\t", "a\tb", "\t\ta\r\n\tb\t"):
        value = _resolve_user_agent(raw, _VERSION)
        assert "\t" not in value
        assert "\r" not in value and "\n" not in value


# --------------------------------------------------------------------------
# Length
# --------------------------------------------------------------------------


def test_the_documented_limit_is_200_characters() -> None:
    assert USER_AGENT_MAX_LENGTH == 200


@pytest.mark.parametrize("length", [201, 500, 10_000])
def test_values_over_the_limit_are_rejected(
    length: int, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    raw = "x" * length
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT
    (record,) = _records(caplog)
    assert record.__dict__["user_agent_reason"] == "too_long"
    assert record.__dict__["user_agent_length"] == length


def test_oversized_rejection_log_is_bounded(caplog: pytest.LogCaptureFixture) -> None:
    # A ten-thousand-character override must not produce a ten-thousand
    # character log line: only the length and the reason are recorded.
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    raw = (_SECRET + "-") * 400
    _resolve_user_agent(raw, _VERSION)
    message = _joined(caplog)
    assert len(message) < 120
    assert _SECRET not in message


# --------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------


def test_values_urllib_cannot_encode_are_rejected_up_front(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # urllib encodes header values as ISO-8859-1; a value outside that range
    # would make *every* request fail with a codec error long after startup.
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    assert _resolve_user_agent("\u0633\u0644\u0627\u0645/1.0", _VERSION) == _DEFAULT
    (record,) = _records(caplog)
    assert record.__dict__["user_agent_reason"] == "unencodable"
    assert "\u0633" not in record.getMessage()


# --------------------------------------------------------------------------
# Safety invariants (fuzz-ish, no network)
# --------------------------------------------------------------------------


def _hostile_values() -> Iterator[str]:
    yield from ("", " ", "\x00", "\t", "\n", "\r", "\r\n", "\x85", "\x7f", "\x1b[31m")
    for code in range(0x00, 0xA0):
        yield f"ua{chr(code)}x"
    yield "x" * 201
    yield "\r\n".join(["a"] * 50)
    yield "a" + "\x00" * 300


@pytest.mark.parametrize("raw", list(_hostile_values()))
def test_resolved_value_is_always_a_single_safe_line(raw: str) -> None:
    value = _resolve_user_agent(raw, _VERSION)
    assert value
    assert 0 < len(value) <= USER_AGENT_MAX_LENGTH
    assert re.search(r"[\x00-\x1f\x7f-\x9f]", value) is None
    value.encode("latin-1")  # never raises: urllib can always send it


def test_resolver_never_raises_on_odd_input() -> None:
    for raw in (None, "", "\x00" * 5, "\ud800", "x" * 100_000):
        assert isinstance(_resolve_user_agent(raw, _VERSION), str)


def test_a_rejected_value_is_never_partially_forwarded() -> None:
    # Rejection is all-or-nothing: no stripping of the bad bytes and sending
    # the rest, which would forward attacker-chosen content anyway.
    raw = "evil/1.0\r\nX-Injected: 1"
    assert _resolve_user_agent(raw, _VERSION) == _DEFAULT
    assert "evil" not in _resolve_user_agent(raw, _VERSION)


# --------------------------------------------------------------------------
# Canonical version source
# --------------------------------------------------------------------------


def test_default_user_agent_uses_the_package_version() -> None:
    assert DEFAULT_USER_AGENT == f"{USER_AGENT_PRODUCT}/{dream.__version__}"


def test_package_version_matches_pyproject() -> None:
    # ``dream.__version__`` is the runtime source; ``pyproject.toml`` is the
    # packaging one. The release checklist keeps them identical, and the
    # User-Agent must follow both, so pin the pair here. A one-line regex
    # keeps this runnable on Python 3.10, which has no ``tomllib``.
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, "pyproject.toml has no [project] version line"
    packaged = match.group(1)
    assert dream.__version__ == packaged
    assert DEFAULT_USER_AGENT.endswith(f"/{packaged}")


def test_default_user_agent_is_not_the_obsolete_pin() -> None:
    assert DEFAULT_USER_AGENT != "dream-assistant/0.1.0"
    assert "0.1.0" not in DEFAULT_USER_AGENT


def test_backend_default_follows_the_package_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DREAM_USER_AGENT", raising=False)
    backend = OpenAIBackend(model="m", api_key="", base_url="http://model.test/v1")
    assert backend.user_agent == f"{USER_AGENT_PRODUCT}/{dream.__version__}"


# --------------------------------------------------------------------------
# Provider request: one header, exact bytes, no network
# --------------------------------------------------------------------------


class _WireCapture:
    """Record the exact bytes ``http.client`` would put on the socket.

    ``urlopen`` is driven through a real ``OpenerDirector`` and a real
    ``HTTPConnection`` whose socket layer is replaced, so header casing,
    ordering, merging and encoding are the stdlib's own; only the network is
    missing. The connection then reports a disconnect, which the backend
    turns into its normal failure reply.
    """

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def opener(self) -> Any:
        capture = self

        class _Connection(http.client.HTTPConnection):
            def connect(self) -> None:
                return None

            def send(self, data: Any) -> None:
                capture.sent.append(bytes(data))

            def getresponse(self) -> Any:
                raise http.client.RemoteDisconnected("captured")

        class _Handler(HTTPHandler):
            def http_open(self, req: Request) -> Any:
                return self.do_open(_Connection, req)

        return build_opener(_Handler)

    def head(self) -> bytes:
        raw = b"".join(self.sent)
        return raw.split(b"\r\n\r\n", 1)[0]

    def header_lines(self, name: bytes) -> list[bytes]:
        prefix = name.lower() + b":"
        return [line for line in self.head().split(b"\r\n")[1:] if line.lower().startswith(prefix)]

    def assert_well_formed(self) -> None:
        """Every header line is one ``Name: value``; no folded continuations."""
        request_line, *headers = self.head().split(b"\r\n")
        assert request_line.startswith(b"POST /v1/chat/completions HTTP/1.1")
        for line in headers:
            assert line, "an empty line would terminate the header block early"
            assert not line.startswith((b" ", b"\t")), line
            assert b":" in line, line
            assert re.search(rb"[\x00-\x08\x0a-\x1f\x7f]", line) is None, line


def _capture_request(
    monkeypatch: pytest.MonkeyPatch, backend: OpenAIBackend, capsys: pytest.CaptureFixture[str]
) -> _WireCapture:
    capture = _WireCapture()
    opener = capture.opener()
    monkeypatch.setattr("dream.agent.urlopen", opener.open)
    backend.chat([{"role": "user", "content": "hi"}], max_retries=0)
    capsys.readouterr()  # the failure line the backend prints for the disconnect
    assert len(capture.sent) >= 1, "the request never reached the connection"
    return capture


def _request_user_agent(request: Request) -> str | None:
    """Return a ``Request``'s User-Agent value, matching the header case-insensitively."""
    for name, value in request.header_items():
        if name.lower() == "user-agent":
            return str(value)
    return None


def test_default_user_agent_is_sent_as_exactly_one_header(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DREAM_USER_AGENT", raising=False)
    backend = OpenAIBackend(model="m", api_key="", base_url="http://model.test/v1")
    capture = _capture_request(monkeypatch, backend, capsys)
    lines = capture.header_lines(b"user-agent")
    assert lines == [f"User-Agent: {DEFAULT_USER_AGENT}".encode("latin-1")]
    capture.assert_well_formed()


def test_custom_user_agent_is_sent_as_exactly_one_header(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DREAM_USER_AGENT", "custom-agent/1.0")
    backend = OpenAIBackend(model="m", api_key="", base_url="http://model.test/v1")
    capture = _capture_request(monkeypatch, backend, capsys)
    assert capture.header_lines(b"user-agent") == [b"User-Agent: custom-agent/1.0"]
    assert b"dream-assistant" not in capture.head()
    capture.assert_well_formed()


def test_rejected_user_agent_sends_the_default_and_nothing_injected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DREAM_USER_AGENT", "evil/1.0\r\n\tX-Injected: yes")
    backend = OpenAIBackend(model="m", api_key="", base_url="http://model.test/v1")
    capture = _capture_request(monkeypatch, backend, capsys)
    head = capture.head()
    assert capture.header_lines(b"user-agent") == [
        f"User-Agent: {DEFAULT_USER_AGENT}".encode("latin-1")
    ]
    assert capture.header_lines(b"x-injected") == []
    assert b"evil" not in head
    capture.assert_well_formed()


def test_user_agent_is_stable_across_retries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Retries reuse ``self.user_agent``; a value resolved once at construction
    # must be sent unchanged on every attempt, with no re-resolution.
    monkeypatch.setenv("DREAM_USER_AGENT", "custom-agent/1.0")
    backend = OpenAIBackend(model="m", api_key="", base_url="http://model.test/v1")
    monkeypatch.setenv("DREAM_USER_AGENT", "changed-later/2.0")
    seen: list[str | None] = []

    def _rate_limited(request: Request, timeout: int | None = None) -> Any:
        seen.append(_request_user_agent(request))
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, BytesIO(b"{}"))

    monkeypatch.setattr("dream.agent.urlopen", _rate_limited)
    monkeypatch.setattr("dream.agent.interruptible_sleep", lambda *_a, **_k: None)
    backend.chat([{"role": "user", "content": "hi"}], max_retries=2)
    capsys.readouterr()
    assert seen == ["custom-agent/1.0"] * 3
    assert backend.user_agent == "custom-agent/1.0"


def test_user_agent_does_not_change_the_request_body_or_auth(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DREAM_USER_AGENT", "custom-agent/1.0")
    backend = OpenAIBackend(model="m", api_key="k-1234", base_url="http://model.test/v1")
    capture = _capture_request(monkeypatch, backend, capsys)
    body = b"".join(capture.sent).split(b"\r\n\r\n", 1)[1]
    assert capture.header_lines(b"authorization") == [b"Authorization: Bearer k-1234"]
    assert capture.header_lines(b"content-type") == [b"Content-Type: application/json"]
    payload = json.loads(body.decode("utf-8"))
    assert payload["model"] == "m"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    assert payload["stream"] is False
    capture.assert_well_formed()


def test_rejection_logs_never_carry_credentials_or_request_data(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    monkeypatch.setenv("DREAM_USER_AGENT", f"{_SECRET}\nX: {_KEYED_URL}")
    backend = OpenAIBackend(model="m", api_key=_SECRET, base_url="http://model.test/v1")
    _capture_request(monkeypatch, backend, capsys)
    message = _joined(caplog)
    assert message, "a rejected override is reported"
    assert _SECRET not in message
    assert "Bearer" not in message
    assert "very-private-value" not in message
    assert "model.test" not in message
    assert "chat/completions" not in message
    assert "X:" not in message
