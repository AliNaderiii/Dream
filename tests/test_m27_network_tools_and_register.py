"""M27 — network lookup tools, the allow-network setting, and register.

Tests are written against the public contract first and run on unchanged
source so the first red names the missing capability, not an import of a
helper that does not exist yet. Every network path is driven by an injected
fetch or resolver; the live network is never called.
"""

from __future__ import annotations

import inspect
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from dream import tools
from dream.agent import _BASE_PROMPT

NETWORK_OFF_MARK = "شبکه"
PRIVATE_MARK = "خصوصی"
REDIRECT_MARK = "مسیر"
TIMEOUT_MARK = "زمان"
TRUNCATED_MARK = "کوتاه"
REGISTER_MARK = "لحن"
CASUAL_INPUT = "سلام خوبی؟ یه کم کمک می‌خوام، گیج شدم."


@pytest.fixture(autouse=True)
def _offline_and_setting_off(monkeypatch):
    """No test in this file may reach the network, and the setting starts off."""

    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)

    def blocked_fetch(*_args, **_kwargs):
        raise AssertionError("test reached the live network via fetch_bytes")

    def blocked_resolve(host: str):
        raise AssertionError(f"test reached the live network via resolve_host({host!r})")

    if hasattr(tools, "fetch_bytes"):
        monkeypatch.setattr(tools, "fetch_bytes", blocked_fetch)
    if hasattr(tools, "resolve_host"):
        monkeypatch.setattr(tools, "resolve_host", blocked_resolve)


def _enable_network(monkeypatch) -> None:
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "1")


def _public_resolve(_host: str) -> list[str]:
    return ["8.8.8.8"]


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _ok_fetch(body: bytes, status: int = 200, headers: dict | None = None, url: str = ""):
    def fetch(requested: str, *, timeout: float, max_bytes: int) -> dict:
        del timeout, max_bytes
        return {
            "status": status,
            "headers": headers or {},
            "body": body,
            "url": url or requested,
        }

    return fetch


def _message(result: object) -> str:
    if isinstance(result, dict):
        parts = [
            str(result.get("message") or ""),
            str(result.get("answer") or ""),
            str(result.get("text") or ""),
        ]
        return " ".join(part for part in parts if part)
    return str(result)


# ---------------------------------------------------------------------------
# Registry and setting
# ---------------------------------------------------------------------------


def test_search_web_and_read_page_are_registered_as_guarded():
    assert "search_web" in tools.REGISTRY, (
        f"search_web must be a registered tool; registry holds {sorted(tools.REGISTRY)}"
    )
    assert "read_page" in tools.REGISTRY, (
        f"read_page must be a registered tool; registry holds {sorted(tools.REGISTRY)}"
    )
    assert tools.REGISTRY["search_web"].risk == "guarded"
    assert tools.REGISTRY["read_page"].risk == "guarded"
    search_props = tools.REGISTRY["search_web"].schema["properties"]
    page_props = tools.REGISTRY["read_page"].schema["properties"]
    assert "query" in tools.REGISTRY["search_web"].schema["required"]
    assert "url" in tools.REGISTRY["read_page"].schema["required"]
    assert "fetch" not in search_props
    assert "fetch" not in page_props


def test_setting_off_refuses_both_tools_and_touches_no_network(monkeypatch):
    called = {"fetch": 0, "resolve": 0}

    def fake_fetch(*_args, **_kwargs):
        called["fetch"] += 1
        raise AssertionError("fetch must not run while the setting is off")

    def fake_resolve(host: str):
        called["resolve"] += 1
        raise AssertionError(f"resolve must not run while the setting is off: {host}")

    monkeypatch.setattr(tools, "fetch_bytes", fake_fetch)
    monkeypatch.setattr(tools, "resolve_host", fake_resolve)

    search = tools.search_web("python courses")
    page = tools.read_page("https://example.com/page")

    assert search["refused"] is True
    assert page["refused"] is True
    assert NETWORK_OFF_MARK in search["message"]
    assert NETWORK_OFF_MARK in page["message"]
    assert called["fetch"] == 0
    assert called["resolve"] == 0

    search_payload = json.loads(tools.execute("search_web", {"query": "x"}))
    page_payload = json.loads(tools.execute("read_page", {"url": "https://example.com/"}))
    assert search_payload["status"] == "ok"
    assert page_payload["status"] == "ok"
    assert search_payload["result"]["refused"] is True
    assert page_payload["result"]["refused"] is True


def test_code_reads_dream_allow_network():
    source = inspect.getsource(tools)
    assert 'os.environ.get("DREAM_ALLOW_NETWORK"' in source


def test_real_fetch_is_the_default_and_is_not_called():
    source = inspect.getsource(tools)
    assert "fetch_bytes = _urllib_fetch_bytes" in source
    impl = inspect.getsource(tools._urllib_fetch_bytes)
    assert "timeout" in impl
    assert "max_bytes" in impl


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_returns_readable_text_never_markup(monkeypatch):
    _enable_network(monkeypatch)
    monkeypatch.setattr(tools, "resolve_host", _public_resolve)
    payload = {
        "AbstractText": "<b>Python</b> is a programming language.",
        "AbstractURL": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "Results": [
            {
                "Text": "<i>Official site</i>",
                "FirstURL": "https://www.python.org/",
            }
        ],
        "RelatedTopics": [
            {
                "Text": "Python (language)",
                "FirstURL": "https://docs.python.org/",
            },
            {
                "Name": "See also",
                "Topics": [
                    {
                        "Text": "Tutorial",
                        "FirstURL": "https://docs.python.org/3/tutorial/",
                    }
                ],
            },
        ],
    }
    seen: list[str] = []

    def fake_fetch(url: str, *, timeout: float, max_bytes: int) -> dict:
        del timeout, max_bytes
        seen.append(url)
        return {"status": 200, "headers": {}, "body": _json_body(payload), "url": url}

    monkeypatch.setattr(tools, "fetch_bytes", fake_fetch)
    result = tools.search_web("python")
    assert result["refused"] is not True
    blob = json.dumps(result, ensure_ascii=False)
    assert "<b>" not in blob
    assert "<i>" not in blob
    assert "Python" in result["answer"]
    assert "programming language" in result["answer"]
    assert result["results"]
    for item in result["results"]:
        assert item["title"]
        assert item["url"].startswith("http")
        assert "<" not in item["title"]
    assert seen, "search must fetch the instant-answer endpoint"
    for url in seen:
        parts = urlsplit(url)
        assert parts.hostname == "api.duckduckgo.com"
        assert "html.duckduckgo" not in url
        assert not parts.path.rstrip("/").endswith("/html")
        query = parse_qs(parts.query)
        assert query.get("format") == ["json"]
        assert query.get("no_html") == ["1"]


def test_search_does_not_attempt_the_bot_challenged_page():
    source = inspect.getsource(tools.search_web)
    module_source = inspect.getsource(tools)
    assert "html.duckduckgo" not in module_source
    assert "api.duckduckgo.com" in module_source
    assert "query" in source


# ---------------------------------------------------------------------------
# Page reader
# ---------------------------------------------------------------------------


def test_page_read_strips_markup_truncates_and_says_so(monkeypatch):
    _enable_network(monkeypatch)
    monkeypatch.setattr(tools, "resolve_host", _public_resolve)
    monkeypatch.setattr(tools, "PAGE_TEXT_CHAR_LIMIT", 40)
    html = (
        "<html><head><style>body{color:red}</style>"
        "<script>alert('x')</script></head>"
        "<body><h1>عنوان</h1><p>Hello <b>world</b> and more readable text "
        "that should be cut.</p></body></html>"
    )
    monkeypatch.setattr(tools, "fetch_bytes", _ok_fetch(html.encode("utf-8")))
    result = tools.read_page("https://example.com/article")
    assert result["refused"] is not True
    text = result["text"]
    assert "<" not in text
    assert "alert" not in text
    assert "color:red" not in text
    assert "Hello" in text
    assert "world" in text
    assert result["truncated"] is True
    assert TRUNCATED_MARK in _message(result)
    assert len(text) <= 40


def test_size_cap_is_enforced_while_reading():
    class CountingStream:
        def __init__(self) -> None:
            self.sent = 0

        def read(self, size: int = -1) -> bytes:
            if self.sent >= 50:
                raise AssertionError("read continued after the size cap")
            take = 8 if size < 0 else min(size, 8, 50 - self.sent)
            if take <= 0:
                return b""
            self.sent += take
            return b"y" * take

    data = tools._read_capped(CountingStream(), max_bytes=50)
    assert len(data) == 50


# ---------------------------------------------------------------------------
# Address refusals and redirects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "http://127.0.0.1/",
        "http://localhost/",
        "http://192.168.1.10/admin",
        "http://10.1.2.3/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://[fe80::1]/",
    ],
)
def test_refused_address_is_persian_not_an_exception(monkeypatch, address):
    _enable_network(monkeypatch)
    called = {"fetch": 0}

    def fake_fetch(*_args, **_kwargs):
        called["fetch"] += 1
        raise AssertionError(f"must not fetch refused address {address}")

    monkeypatch.setattr(tools, "fetch_bytes", fake_fetch)
    monkeypatch.setattr(tools, "resolve_host", _public_resolve)
    result = tools.read_page(address)
    assert result["refused"] is True
    assert any(mark in result["message"] for mark in (PRIVATE_MARK, "مجاز", "نشانی"))
    assert called["fetch"] == 0
    payload = json.loads(tools.execute("read_page", {"url": address}))
    assert payload["status"] == "ok"
    assert payload["result"]["refused"] is True


def test_hostname_resolving_to_private_is_refused(monkeypatch):
    _enable_network(monkeypatch)

    def fake_fetch(*_args, **_kwargs):
        raise AssertionError("must not fetch a host that resolved private")

    monkeypatch.setattr(tools, "fetch_bytes", fake_fetch)
    monkeypatch.setattr(tools, "resolve_host", lambda _host: ["10.0.0.8"])
    result = tools.read_page("https://intranet.example/")
    assert result["refused"] is True
    assert PRIVATE_MARK in result["message"]


def test_redirect_to_refused_address_is_refused_not_followed(monkeypatch):
    _enable_network(monkeypatch)
    calls: list[str] = []

    def fake_fetch(url: str, *, timeout: float, max_bytes: int) -> dict:
        del timeout, max_bytes
        calls.append(url)
        if "127.0.0.1" in url or "169.254." in url:
            raise AssertionError(f"redirect to refused address was followed: {url}")
        return {
            "status": 302,
            "headers": {"Location": "http://127.0.0.1/secret"},
            "body": b"",
            "url": url,
        }

    monkeypatch.setattr(tools, "fetch_bytes", fake_fetch)
    monkeypatch.setattr(tools, "resolve_host", _public_resolve)
    result = tools.read_page("https://public.example/start")
    assert result["refused"] is True
    assert REDIRECT_MARK in result["message"] or PRIVATE_MARK in result["message"]
    assert calls == ["https://public.example/start"]


def test_timeout_returns_persian_refusal_not_exception(monkeypatch):
    _enable_network(monkeypatch)

    def fake_fetch(url: str, *, timeout: float, max_bytes: int) -> dict:
        del url, max_bytes
        assert timeout == tools.NETWORK_TIMEOUT_SECONDS
        raise TimeoutError("simulated hang")

    monkeypatch.setattr(tools, "fetch_bytes", fake_fetch)
    monkeypatch.setattr(tools, "resolve_host", _public_resolve)
    result = tools.read_page("https://example.com/slow")
    assert result["refused"] is True
    assert TIMEOUT_MARK in result["message"]
    payload = json.loads(tools.execute("read_page", {"url": "https://example.com/slow"}))
    assert payload["status"] == "ok"
    assert payload["result"]["refused"] is True


def test_default_transport_has_a_hard_timeout():
    source = inspect.getsource(tools._urllib_fetch_bytes)
    assert "timeout=timeout" in source
    assert 0 < tools.NETWORK_TIMEOUT_SECONDS <= 30


# ---------------------------------------------------------------------------
# Prompt: register, and the internet sentence is no longer a lie
# ---------------------------------------------------------------------------


def test_prompt_carries_a_register_instruction():
    assert REGISTER_MARK in _BASE_PROMPT
    assert "خودمانی" in _BASE_PROMPT
    assert "رسمی" in _BASE_PROMPT


def test_prompt_no_longer_claims_it_cannot_reach_the_internet():
    assert "دسترسی به اینترنت نداری" not in _BASE_PROMPT
    assert "پیشنهاد جستجو نده" not in _BASE_PROMPT
    assert "search_web" in _BASE_PROMPT
    assert "read_page" in _BASE_PROMPT
    assert "شبکه" in _BASE_PROMPT


class RegisterTranscriptProbe:
    """Deterministic stand-in: the reply is driven only by the prompt text."""

    def reply(self, prompt: str, question: str) -> str:
        del question
        if REGISTER_MARK not in prompt:
            return (
                "با سلام و احترام. در خدمت جنابعالی هستم. "
                "لطفاً موضوع را به صورت کامل مرقوم فرمایید."
            )
        return "سلام، باشه کمک می‌کنم. بگو کجا گیر کردی."


def test_casual_persian_message_gets_a_casual_answer_after_register_instruction(capsys):
    probe = RegisterTranscriptProbe()
    before_prompt = _BASE_PROMPT.replace(
        "لحن پاسخ را با لحن نویسنده یکی کن؛ پیام خودمانی را خودمانی، "
        "رسمی را رسمی، و پیام پریشان را ساده و گرم جواب بده نه با قالب. ",
        "",
    )
    before = probe.reply(before_prompt, CASUAL_INPUT)
    after = probe.reply(_BASE_PROMPT, CASUAL_INPUT)
    print(f"input:  {CASUAL_INPUT}")
    print(f"before: {before}")
    print(f"after:  {after}")
    assert before != after
    assert "جنابعالی" in before
    assert "سلام" in after
    assert "مرقوم" not in after
    captured = capsys.readouterr().out
    assert CASUAL_INPUT in captured
    assert before in captured
    assert after in captured
