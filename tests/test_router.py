"""S00 model router: hosted → Ollama → BYOK → echo with a privacy sentence.

Pins the acceptance criteria for the router:

- Priority is fixed: hosted → Ollama → BYOK → echo.
- An explicit ``DREAM_BACKEND`` wins over the priority fallback.
- Every resolved route carries an English and a Persian sentence stating
  whether data leaves the machine.
- ``dream --route`` and ``/route`` print that disclosure and exit cleanly.
- Resolution never touches the network: it is deterministic from the
  environment, so the whole router is offline-testable.
"""

from __future__ import annotations

import re

import pytest

import cli
from dream.agent import Dream, EchoBackend, OllamaBackend, OpenAIBackend
from dream.memory import MemoryStore
from dream.router import build_router_backend, resolve_route, route_text

PERSIAN = re.compile(r"[\u0600-\u06FF]")


@pytest.fixture(autouse=True)
def _clean_router_env(monkeypatch):
    """Every router test starts from a clean routing environment."""
    for name in (
        "DREAM_BACKEND",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OLLAMA_HOST",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_route_is_echo_and_nothing_leaves():
    route = resolve_route()
    assert route.name == "echo"
    assert route.leaves_machine is False
    assert "no data leaves" in route.sentence_en.lower()
    assert PERSIAN.search(route.sentence_fa)


def test_openai_key_selects_hosted_route(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    route = resolve_route()
    assert route.name == "hosted"
    assert route.leaves_machine is True
    assert "leaves this machine" in route.sentence_en.lower()
    assert PERSIAN.search(route.sentence_fa)


def test_ollama_host_selects_local_route(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    route = resolve_route()
    assert route.name == "ollama"
    assert route.leaves_machine is False
    assert "never leaves" in route.sentence_en.lower()
    assert PERSIAN.search(route.sentence_fa)


def test_custom_base_url_selects_byok(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://my-gateway.example.com/v1")
    route = resolve_route()
    assert route.name == "byok"
    assert route.leaves_machine is True
    assert PERSIAN.search(route.sentence_fa)


def test_hosted_beats_ollama_when_both_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    assert resolve_route().name == "hosted"


def test_ollama_beats_echo_when_configured(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    assert resolve_route().name == "ollama"


def test_explicit_backend_mapping(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "openai")
    assert resolve_route().name == "hosted"
    monkeypatch.setenv("DREAM_BACKEND", "ollama")
    assert resolve_route().name == "ollama"
    monkeypatch.setenv("DREAM_BACKEND", "echo")
    assert resolve_route().name == "echo"


def test_explicit_openai_with_custom_base_url_is_byok(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://my-gateway.example.com/v1")
    assert resolve_route().name == "byok"


def test_every_route_carries_both_privacy_sentences(monkeypatch):
    import dream.router as router_module

    for route in (
        router_module._HOSTED,
        router_module._OLLAMA,
        router_module._BYOK,
        router_module._ECHO,
    ):
        assert route.sentence_en.strip()
        assert route.sentence_fa.strip()
        assert PERSIAN.search(route.sentence_fa)
        assert "leaves" in route.sentence_en.lower() or "offline" in route.sentence_en.lower()


def test_route_text_is_bilingual_and_named(monkeypatch):
    text = route_text()
    assert "Route: echo" in text
    assert PERSIAN.search(text)


def test_build_router_backend_matches_route(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "echo")
    assert isinstance(build_router_backend(), EchoBackend)
    monkeypatch.setenv("DREAM_BACKEND", "ollama")
    assert isinstance(build_router_backend(), OllamaBackend)
    monkeypatch.setenv("DREAM_BACKEND", "openai")
    assert isinstance(build_router_backend(), OpenAIBackend)
    monkeypatch.delenv("DREAM_BACKEND")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert isinstance(build_router_backend(), OpenAIBackend)


def test_cli_route_flag_exits_zero(monkeypatch, capsys):
    assert cli.main(["--route"]) == 0
    out = capsys.readouterr().out
    assert "Route: echo" in out
    assert "no data leaves this machine" in out.lower()


def test_slash_route_dispatch(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        lines: list[str] = []
        assert cli.dispatch_command("/route", dream, lines.append) is True
        joined = "\n".join(lines)
        assert "Route:" in joined
        assert PERSIAN.search(joined)


def test_cli_plan_flag_and_route_flag_do_not_touch_network(monkeypatch, capsys):
    """Both informational flags return 0 with no backend construction."""
    assert cli.main(["--plan"]) == 0
    assert cli.main(["--route"]) == 0
    out = capsys.readouterr().out
    assert "IRR" in out
