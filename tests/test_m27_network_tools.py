"""Offline contract tests for M27's owner-enabled network tools."""

from __future__ import annotations

import inspect
import socket
from urllib.error import URLError
from urllib.request import Request

import pytest

from dream import agent, tools


class FakeResponse:
    """A byte-stream response which honours the caller's bounded reads."""

    def __init__(self, body: bytes, final_url: str) -> None:
        self._body = body
        self._position = 0
        self._final_url = final_url

    def read(self, amount: int = -1) -> bytes:
        if amount < 0:
            amount = len(self._body) - self._position
        chunk = self._body[self._position : self._position + amount]
        self._position += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self._final_url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _public_dns(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


@pytest.fixture
def network_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")
    monkeypatch.setattr(tools.socket, "getaddrinfo", _public_dns)


def test_search_returns_plain_answer_and_related_links_without_markup(
    monkeypatch: pytest.MonkeyPatch, network_enabled: None
) -> None:
    body = b'''{"AbstractText":"<b>Plain</b> answer", "RelatedTopics":[
        {"Text":"<i>Related</i> result", "FirstURL":"https://example.com/topic"}
    ]}'''
    monkeypatch.setattr(
        tools,
        "_open_network_request",
        lambda request, timeout: FakeResponse(body, request.full_url),
    )

    result = tools.search_web("plain answer")

    assert "Plain answer" in result
    assert "Related result" in result
    assert "https://example.com/topic" in result
    assert "<b>" not in result and "<i>" not in result


def test_read_page_strips_markup_truncates_at_stated_cap_and_reads_in_bounded_chunks(
    monkeypatch: pytest.MonkeyPatch, network_enabled: None
) -> None:
    body = (
        b"<html><body><h1>Title</h1><p>"
        + b"x" * (tools.PAGE_TEXT_CAP * 2)
        + b"</p></body></html>"
    )
    reads: list[int] = []

    class MeasuredResponse(FakeResponse):
        def read(self, amount: int = -1) -> bytes:
            reads.append(amount)
            return super().read(amount)

    monkeypatch.setattr(
        tools,
        "_open_network_request",
        lambda request, timeout: MeasuredResponse(body, request.full_url),
    )

    result = tools.read_page("https://example.com/long")

    assert "Title" in result
    assert "<html" not in result and "<p>" not in result
    assert f"{tools.PAGE_TEXT_CAP}" in result
    assert "truncated" in result.lower()
    assert max(reads) <= tools.PAGE_RESPONSE_CAP + 1


def test_refused_scheme_and_private_or_loopback_addresses_return_persian_refusal(
    monkeypatch: pytest.MonkeyPatch, network_enabled: None
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(tools, "_open_network_request", lambda *_args: calls.append(1))

    for address in ("file:///etc/passwd", "http://127.0.0.1/private", "http://localhost/private"):
        result = tools.read_page(address)
        assert tools.NETWORK_REFUSAL_MESSAGE in result

    assert calls == []


def test_redirect_to_private_destination_is_refused_before_following(
    monkeypatch: pytest.MonkeyPatch, network_enabled: None
) -> None:
    monkeypatch.setattr(tools.socket, "getaddrinfo", _public_dns)
    handler = tools._RestrictedRedirectHandler()
    request = Request("https://example.com/start")

    with pytest.raises(tools._AddressRefused):
        handler.redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1/private")


def test_timeout_returns_persian_refusal_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, network_enabled: None
) -> None:
    def timeout(_request: Request, _timeout: float) -> FakeResponse:
        raise URLError("timed out")

    monkeypatch.setattr(tools, "_open_network_request", timeout)

    assert tools.NETWORK_REFUSAL_MESSAGE in tools.search_web("anything")


def test_setting_off_refuses_both_tools_without_touching_dns_or_network(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network must not be touched when disabled")

    monkeypatch.setattr(tools.socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(tools, "_open_network_request", forbidden)

    assert tools.NETWORK_DISABLED_MESSAGE in tools.search_web("anything")
    assert tools.NETWORK_DISABLED_MESSAGE in tools.read_page("https://example.com")


def test_tools_are_registered_guarded_and_use_a_hard_timeout_and_response_caps() -> None:
    assert tools.REGISTRY["search_web"].risk == "guarded"
    assert tools.REGISTRY["read_page"].risk == "guarded"
    assert tools.NETWORK_TIMEOUT_SECONDS == 10
    assert tools.SEARCH_RESPONSE_CAP == 100_000
    assert tools.PAGE_RESPONSE_CAP == 250_000
    assert tools._open_network_request is tools._default_open_network_request


def test_prompt_replaces_no_internet_claim_with_owner_enabled_truth() -> None:
    prompt = agent._BASE_PROMPT
    assert "search_web" in prompt and "read_page" in prompt
    assert "DREAM_ALLOW_NETWORK" in prompt
    assert "اینترنت نداری" not in prompt


def test_fetching_is_injected_by_patch_not_real_network() -> None:
    source = inspect.getsource(tools)
    assert "_open_network_request" in source
    assert "build_opener" in source
