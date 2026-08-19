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


# ---------------------------------------------------------------------------
# S01: the full priority table — hosted → Ollama → BYOK → echo
# ---------------------------------------------------------------------------

OFFICIAL = "https://api.openai.com/v1"
CUSTOM = "https://my-gateway.example.com/v1"
LOCAL_OLLAMA = "http://localhost:11434"


def _set(monkeypatch, **env):
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    ("key", "base_url", "ollama_host", "expected"),
    [
        # Nothing configured: offline echo.
        (None, None, None, "echo"),
        # An official key wins over everything below it.
        ("sk-test", None, None, "hosted"),
        ("sk-test", OFFICIAL, None, "hosted"),
        ("sk-test", None, LOCAL_OLLAMA, "hosted"),
        ("sk-test", OFFICIAL, LOCAL_OLLAMA, "hosted"),
        # No official key: a local Ollama outranks a BYOK endpoint.
        (None, None, LOCAL_OLLAMA, "ollama"),
        (None, CUSTOM, LOCAL_OLLAMA, "ollama"),
        ("sk-test", CUSTOM, LOCAL_OLLAMA, "ollama"),
        # No Ollama: a custom endpoint is BYOK, with or without a key.
        ("sk-test", CUSTOM, None, "byok"),
        (None, CUSTOM, None, "byok"),
        # An official base URL with no key is not a route: fall through.
        (None, OFFICIAL, None, "echo"),
    ],
)
def test_router_priority_table(monkeypatch, key, base_url, ollama_host, expected):
    _set(
        monkeypatch,
        OPENAI_API_KEY=key,
        OPENAI_BASE_URL=base_url,
        OLLAMA_HOST=ollama_host,
    )
    assert resolve_route().name == expected


def test_ollama_beats_byok_without_an_official_key(monkeypatch):
    """The local server is the more private option, so it wins."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-byok")
    monkeypatch.setenv("OPENAI_BASE_URL", CUSTOM)
    monkeypatch.setenv("OLLAMA_HOST", LOCAL_OLLAMA)
    route = resolve_route()
    assert route.name == "ollama"
    assert route.leaves_machine is False


def test_hosted_beats_ollama_with_an_official_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-official")
    monkeypatch.setenv("OPENAI_BASE_URL", OFFICIAL)
    monkeypatch.setenv("OLLAMA_HOST", LOCAL_OLLAMA)
    route = resolve_route()
    assert route.name == "hosted"
    assert route.leaves_machine is True


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "https://api.openai.com/v1/",
        "  https://api.openai.com/v1  ",
        "HTTPS://API.OPENAI.COM/v1",
    ],
)
def test_official_base_url_spellings_stay_hosted(monkeypatch, base_url):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    assert resolve_route().name == "hosted"


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com.evil.example/v1",
        "http://api.openai.com/v1",  # plain http is not the official endpoint
        "https://openai.example.com/v1",
    ],
)
def test_lookalike_base_urls_are_byok_not_hosted(monkeypatch, base_url):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    assert resolve_route().name == "byok"


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_env_values_are_ignored(monkeypatch, blank):
    monkeypatch.setenv("OPENAI_API_KEY", blank)
    monkeypatch.setenv("OPENAI_BASE_URL", blank)
    monkeypatch.setenv("OLLAMA_HOST", blank)
    assert resolve_route().name == "echo"


def test_blank_backend_env_falls_back_to_priority(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "   ")
    monkeypatch.setenv("OLLAMA_HOST", LOCAL_OLLAMA)
    assert resolve_route().name == "ollama"


def test_unknown_backend_env_falls_back_to_priority(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "banana")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_route().name == "hosted"


@pytest.mark.parametrize("raw", ["echo", "ECHO", "  Echo  "])
def test_explicit_backend_is_case_and_whitespace_insensitive(monkeypatch, raw):
    monkeypatch.setenv("DREAM_BACKEND", raw)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_HOST", LOCAL_OLLAMA)
    assert resolve_route().name == "echo"


def test_explicit_ollama_wins_over_an_official_key(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "ollama")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_route().name == "ollama"


def test_byok_backend_is_still_an_openai_backend(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", CUSTOM)
    assert resolve_route().name == "byok"
    assert isinstance(build_router_backend(), OpenAIBackend)


def test_ollama_route_builds_an_ollama_backend(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-byok")
    monkeypatch.setenv("OPENAI_BASE_URL", CUSTOM)
    monkeypatch.setenv("OLLAMA_HOST", LOCAL_OLLAMA)
    assert isinstance(build_router_backend(), OllamaBackend)


def test_route_names_are_exactly_the_four_documented_ones(monkeypatch):
    import dream.router as router_module

    names = {
        router_module._HOSTED.name,
        router_module._OLLAMA.name,
        router_module._BYOK.name,
        router_module._ECHO.name,
    }
    assert names == {"hosted", "ollama", "byok", "echo"}
    assert set(router_module._ROUTE_BACKEND) == names


def test_only_local_routes_claim_data_stays_put(monkeypatch):
    import dream.router as router_module

    assert router_module._OLLAMA.leaves_machine is False
    assert router_module._ECHO.leaves_machine is False
    assert router_module._HOSTED.leaves_machine is True
    assert router_module._BYOK.leaves_machine is True


def test_route_text_never_prints_the_api_key(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", CUSTOM)
    assert cli.main(["--route"]) == 0
    out = capsys.readouterr().out
    assert "sk-super-secret-value" not in out
    assert "Route: byok" in out
    assert PERSIAN.search(out)


def test_resolve_route_does_not_mutate_the_environment(monkeypatch):
    import os

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    before = dict(os.environ)
    resolve_route()
    route_text()
    assert dict(os.environ) == before
