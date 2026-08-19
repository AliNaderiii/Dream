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
        "AVALAI_API_KEY",
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
        router_module._AVAL,
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
AVAL = "https://api.avalai.ir/v1"
AVAL_FALLBACK = "https://api.avalapis.ir/v1"


def _set(monkeypatch, **env):
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    ("key", "base_url", "ollama_host", "aval_key", "expected"),
    [
        # Nothing configured: offline echo.
        (None, None, None, None, "echo"),
        # An official key wins over everything below it.
        ("sk-test", None, None, None, "hosted"),
        ("sk-test", OFFICIAL, None, None, "hosted"),
        ("sk-test", None, LOCAL_OLLAMA, None, "hosted"),
        ("sk-test", OFFICIAL, LOCAL_OLLAMA, None, "hosted"),
        # An official key and base still beat an Aval key: the user's
        # explicit hosted configuration wins.
        ("sk-test", OFFICIAL, None, "sk-aval", "hosted"),
        ("sk-test", None, None, "sk-aval", "hosted"),
        # An Aval key or Aval base selects the aval route; it outranks a
        # local Ollama but sits below the official hosted route.
        (None, None, None, "sk-aval", "aval"),
        (None, AVAL, None, None, "aval"),
        (None, AVAL_FALLBACK, None, None, "aval"),
        (None, None, LOCAL_OLLAMA, "sk-aval", "aval"),
        (None, AVAL, LOCAL_OLLAMA, None, "aval"),
        # An OPENAI_API_KEY pointed at an Aval base is the Aval route: the
        # endpoint names Aval, so the honest route name is aval, not byok.
        ("sk-test", AVAL, None, None, "aval"),
        ("sk-test", AVAL, LOCAL_OLLAMA, None, "aval"),
        # No official key: a local Ollama outranks a BYOK endpoint.
        (None, None, LOCAL_OLLAMA, None, "ollama"),
        (None, CUSTOM, LOCAL_OLLAMA, None, "ollama"),
        ("sk-test", CUSTOM, LOCAL_OLLAMA, None, "ollama"),
        # No Ollama: a custom endpoint is BYOK, with or without a key.
        ("sk-test", CUSTOM, None, None, "byok"),
        (None, CUSTOM, None, None, "byok"),
        # An official base URL with no key is not a route: fall through.
        (None, OFFICIAL, None, None, "echo"),
    ],
)
def test_router_priority_table(monkeypatch, key, base_url, ollama_host, aval_key, expected):
    _set(
        monkeypatch,
        OPENAI_API_KEY=key,
        OPENAI_BASE_URL=base_url,
        OLLAMA_HOST=ollama_host,
        AVALAI_API_KEY=aval_key,
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
    monkeypatch.setenv("AVALAI_API_KEY", blank)
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


# ---------------------------------------------------------------------------
# S09: the named Aval route — the recommended hosted path for Iranian users.
# ---------------------------------------------------------------------------


def test_aval_key_selects_aval_route(monkeypatch):
    monkeypatch.setenv("AVALAI_API_KEY", "sk-aval")
    route = resolve_route()
    assert route.name == "aval"
    assert route.leaves_machine is True
    assert "aval ai" in route.sentence_en.lower()
    assert "api.avalai.ir" in route.sentence_en.lower()
    assert "leaves this machine" in route.sentence_en.lower()
    assert PERSIAN.search(route.sentence_fa)
    assert "aval ai" in route.sentence_fa.lower()


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.avalai.ir/v1",
        "https://api.avalai.ir/v1/",
        "  HTTPS://API.AVALAI.IR/v1  ",
        "https://api.avalapis.ir/v1",
        "https://api.avalapis.ir/v1/",
    ],
)
def test_aval_base_url_spellings_select_aval_route(monkeypatch, base_url):
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    assert resolve_route().name == "aval"


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.avalai.ir.evil.example/v1",
        "https://avalai.ir/v1",
        "https://api.avalapis.ir.evil.example/v1",
        "https://avalai.ir.evil.example/v1",
    ],
)
def test_aval_lookalike_base_urls_are_byok_not_aval(monkeypatch, base_url):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    assert resolve_route().name == "byok"


@pytest.mark.parametrize("raw", ["aval", "avalai", "AVAL", "  Aval  "])
def test_explicit_aval_backend_selects_aval_route(monkeypatch, raw):
    monkeypatch.setenv("DREAM_BACKEND", raw)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_HOST", LOCAL_OLLAMA)
    route = resolve_route()
    assert route.name == "aval"
    assert route.leaves_machine is True


def test_explicit_openai_with_aval_base_is_aval(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", AVAL)
    assert resolve_route().name == "aval"


def test_aval_beats_ollama_when_both_configured(monkeypatch):
    monkeypatch.setenv("AVALAI_API_KEY", "sk-aval")
    monkeypatch.setenv("OLLAMA_HOST", LOCAL_OLLAMA)
    route = resolve_route()
    assert route.name == "aval"
    assert route.leaves_machine is True


def test_official_key_and_base_still_beat_aval_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-official")
    monkeypatch.setenv("OPENAI_BASE_URL", OFFICIAL)
    monkeypatch.setenv("AVALAI_API_KEY", "sk-aval")
    assert resolve_route().name == "hosted"


def test_aval_route_builds_an_openai_backend(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "aval")
    assert resolve_route().name == "aval"
    assert isinstance(build_router_backend(), OpenAIBackend)


def test_echo_and_demo_stay_offline_even_when_aval_configured(monkeypatch):
    monkeypatch.setenv("DREAM_BACKEND", "echo")
    monkeypatch.setenv("AVALAI_API_KEY", "sk-aval")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    route = resolve_route()
    assert route.name == "echo"
    assert route.leaves_machine is False


def test_aval_resolution_never_probes_the_network(monkeypatch):
    """The aval route is decided from the environment alone: any attempt to
    open a connection during resolution fails the test (no live Aval call in
    CI, and none anywhere else in the router)."""
    import urllib.request

    def _forbid(*_args, **_kwargs):
        raise AssertionError("route resolution must never open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbid)
    monkeypatch.setenv("AVALAI_API_KEY", "sk-aval")
    assert resolve_route().name == "aval"
    text = route_text()
    assert "Route: aval" in text
    assert PERSIAN.search(text)


def test_route_names_are_exactly_the_five_documented_ones(monkeypatch):
    import dream.router as router_module

    names = {
        router_module._HOSTED.name,
        router_module._AVAL.name,
        router_module._OLLAMA.name,
        router_module._BYOK.name,
        router_module._ECHO.name,
    }
    assert names == {"hosted", "aval", "ollama", "byok", "echo"}
    assert set(router_module._ROUTE_BACKEND) == names


def test_only_local_routes_claim_data_stays_put(monkeypatch):
    import dream.router as router_module

    assert router_module._OLLAMA.leaves_machine is False
    assert router_module._ECHO.leaves_machine is False
    assert router_module._HOSTED.leaves_machine is True
    assert router_module._AVAL.leaves_machine is True
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
