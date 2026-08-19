"""Model router: hosted → Aval → Ollama → BYOK → echo, with an honest privacy line.

The router resolves which backend a turn would use without calling the
network. The priority is fixed:

1. ``hosted`` — the official cloud model service configured with
   ``OPENAI_API_KEY`` (or ``DREAM_BACKEND=openai``). Messages leave the
   machine.
2. ``aval`` — Aval AI, the recommended hosted path for Iranian users:
   ``AVALAI_API_KEY`` set, ``OPENAI_BASE_URL`` pointing at api.avalai.ir /
   api.avalapis.ir, or ``DREAM_BACKEND=aval`` / ``avalai``. Messages leave
   the machine for Aval (api.avalai.ir). Never probed: detection is
   deterministic from the environment only.
3. ``ollama`` — a local Ollama server configured with ``OLLAMA_HOST``
   (or ``DREAM_BACKEND=ollama``). Messages never leave the machine.
4. ``byok`` — bring your own key/endpoint: ``OPENAI_BASE_URL`` points at a
   user-chosen server (with ``DREAM_BACKEND=openai`` or a key). Messages
   leave the machine to that server. A configured local Ollama outranks
   BYOK: without an official key, the private local server wins.
5. ``echo`` — the deterministic offline backend. Nothing leaves the machine.

Every resolved route carries a sentence (English and Persian) that states
whether data leaves the machine, so ``dream --route`` / ``/route`` can never
hand-wave the privacy question.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

OFFICIAL_BASE_URLS = ("https://api.openai.com/v1", "https://api.openai.com/v1/")

# Aval AI documents two OpenAI-compatible hosts. The primary endpoint is
# https://api.avalai.ir/v1; https://api.avalapis.ir/v1 is the fallback host.
# Both are recognised for routing, but neither is ever probed here.
AVAL_BASE_URLS = (
    "https://api.avalai.ir/v1",
    "https://api.avalai.ir/v1/",
    "https://api.avalapis.ir/v1",
    "https://api.avalapis.ir/v1/",
)


@dataclass(frozen=True)
class Route:
    """One resolved route and its privacy statement."""

    name: str
    leaves_machine: bool
    sentence_en: str
    sentence_fa: str


_HOSTED = Route(
    name="hosted",
    leaves_machine=True,
    sentence_en=(
        "Route: hosted — this turn is sent to a cloud model service; "
        "your message leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0633\u0631\u0648\u06cc\u0633 \u0627\u0628\u0631\u06cc "
        "\u2014 \u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 \u06cc\u06a9 "
        "\u0633\u0631\u0648\u06cc\u0633 \u0645\u062f\u0644 \u0627\u0628\u0631\u06cc "
        "\u0641\u0631\u0633\u062a\u0627\u062f\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f\u061b "
        "\u067e\u06cc\u0627\u0645 \u0634\u0645\u0627 \u0627\u0632 \u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)

_AVAL = Route(
    name="aval",
    leaves_machine=True,
    sentence_en=(
        "Route: aval — this turn is sent to Aval AI (api.avalai.ir), "
        "the Iranian cloud provider you configured; "
        "your message leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0622\u0648\u0627\u0644 \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 Aval AI "
        "(api.avalai.ir) \u0641\u0631\u0633\u062a\u0627\u062f\u0647 "
        "\u0645\u06cc\u0634\u0648\u062f\u061b \u067e\u06cc\u0627\u0645 "
        "\u0634\u0645\u0627 \u0627\u0632 \u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0645\u06cc\u0634\u0648\u062f."
    ),
)

_OLLAMA = Route(
    name="ollama",
    leaves_machine=False,
    sentence_en=(
        "Route: ollama — this turn runs against a local Ollama server; "
        "your message never leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0627\u0648\u0644\u0627\u0645\u0627 \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0631\u0648\u06cc \u0633\u0631\u0648\u0631 "
        "\u0645\u062d\u0644\u06cc \u0627\u0648\u0644\u0627\u0645\u0627 \u0627\u062c\u0631\u0627 "
        "\u0645\u06cc\u200c\u0634\u0648\u062f\u061b \u067e\u06cc\u0627\u0645 \u0634\u0645\u0627 "
        "\u0647\u0631\u06af\u0632 \u0627\u0632 \u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 "
        "\u062e\u0627\u0631\u062c \u0646\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)

_BYOK = Route(
    name="byok",
    leaves_machine=True,
    sentence_en=(
        "Route: byok — this turn is sent to the endpoint you configured "
        "yourself; your message leaves this machine for that server."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u06a9\u0644\u06cc\u062f \u0634\u062e\u0635\u06cc \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 \u0633\u0631\u0648\u0631\u06cc "
        "\u06a9\u0647 \u062e\u0648\u062f\u062a\u0627\u0646 "
        "\u067e\u06cc\u06a9\u0631\u0628\u0646\u062f\u06cc "
        "\u06a9\u0631\u062f\u0647\u200c\u0627\u06cc\u062f "
        "\u0641\u0631\u0633\u062a\u0627\u062f\u0647 "
        "\u0645\u06cc\u200c\u0634\u0648\u062f\u061b \u067e\u06cc\u0627\u0645 \u0634\u0645\u0627 "
        "\u0628\u0631\u0627\u06cc \u0622\u0646 \u0633\u0631\u0648\u0631 \u0627\u0632 "
        "\u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)

_ECHO = Route(
    name="echo",
    leaves_machine=False,
    sentence_en=(
        "Route: echo — fully offline echo backend; "
        "no data leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0622\u0641\u0644\u0627\u06cc\u0646 \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 \u0635\u0648\u0631\u062a "
        "\u06a9\u0627\u0645\u0644\u0627\u064b \u0622\u0641\u0644\u0627\u06cc\u0646 "
        "\u067e\u0631\u062f\u0627\u0632\u0634 \u0645\u06cc\u200c\u0634\u0648\u062f\u061b "
        "\u0647\u06cc\u0686 \u062f\u0627\u062f\u0647\u200c\u0627\u06cc \u0627\u0632 "
        "\u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def resolve_route() -> Route:
    """Pick the active route by configuration, never by network probes.

    An explicit ``DREAM_BACKEND`` wins; otherwise the fixed priority
    hosted → Aval → Ollama → BYOK → echo applies:

    - ``hosted`` needs an API key *and* the official base URL (an unset base
      URL means the official default). An official key and base outrank an
      Aval key: the user's explicit hosted configuration wins.
    - ``aval`` needs ``AVALAI_API_KEY`` or an Aval base URL
      (api.avalai.ir / api.avalapis.ir). It sits below hosted but above the
      local Ollama server: the user configured a cloud provider on purpose.
    - a configured local Ollama beats BYOK: when the key points at somebody
      else's endpoint, the local server is the more private option and wins.
    - ``byok`` needs a custom (non-official, non-Aval) base URL. An official
      base URL with no key is not a route at all, so it falls through to echo.

    The result is deterministic and offline-testable; nothing here opens a
    network connection.
    """
    explicit = _env("DREAM_BACKEND").lower()
    base_url = _env("OPENAI_BASE_URL")
    official_base = _is_official_base(base_url)
    aval_base = _is_aval_base(base_url)
    if explicit in ("aval", "avalai"):
        return _AVAL
    if explicit == "openai":
        if official_base:
            return _HOSTED
        return _AVAL if aval_base else _BYOK
    if explicit == "ollama":
        return _OLLAMA
    if explicit == "echo":
        return _ECHO

    if _env("OPENAI_API_KEY") and official_base:
        return _HOSTED
    # Read literally (not via _env) so the settings-example rule M23 can see
    # that the documented AVALAI_API_KEY name is a real environment read.
    if (os.environ.get("AVALAI_API_KEY") or "").strip() or aval_base:
        return _AVAL
    if _env("OLLAMA_HOST"):
        return _OLLAMA
    if base_url and not official_base:
        return _BYOK
    return _ECHO


def _is_official_base(base_url: str) -> bool:
    """True when the endpoint is the official OpenAI-compatible host.

    Comparison ignores a trailing slash and surrounding case in the scheme
    and host, so ``HTTPS://API.OPENAI.COM/v1/`` is still the official base
    and does not masquerade as a BYOK endpoint.
    """
    if not base_url:
        return True  # empty means the official default
    normalised = base_url.strip().rstrip("/")
    return normalised.lower() in {url.rstrip("/").lower() for url in OFFICIAL_BASE_URLS}


def _is_aval_base(base_url: str) -> bool:
    """True when the endpoint is Aval AI's OpenAI-compatible host.

    Both documented Aval hosts count — api.avalai.ir and the api.avalapis.ir
    fallback — so an ``OPENAI_BASE_URL`` pointed at Aval is honestly named the
    ``aval`` route rather than a generic BYOK endpoint. The comparison ignores
    a trailing slash and surrounding case, and it never touches the network.
    An unset base URL means the official OpenAI default, so it is never Aval.
    """
    if not base_url:
        return False
    normalised = base_url.strip().rstrip("/")
    return normalised.lower() in {url.rstrip("/").lower() for url in AVAL_BASE_URLS}


# Maps a route name to the backend name ``build_backend`` understands.
# Aval is OpenAI-compatible, so the aval route builds the same client the
# hosted and byok routes use.
_ROUTE_BACKEND: dict[str, str] = {
    "hosted": "openai",
    "aval": "openai",
    "ollama": "ollama",
    "byok": "openai",
    "echo": "echo",
}


def build_router_backend():
    """Construct the backend instance the resolved route would use."""
    from dream.agent import build_backend

    return build_backend(_ROUTE_BACKEND[resolve_route().name])


def route_text() -> str:
    """One honest paragraph naming the route and whether data leaves."""
    route = resolve_route()
    return f"{route.sentence_en}\n{route.sentence_fa}"

