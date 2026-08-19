"""Model router: hosted → Ollama → BYOK → echo, with an honest privacy line.

The router resolves which backend a turn would use without calling the
network. The priority is fixed:

1. ``hosted`` — a cloud model service configured with ``OPENAI_API_KEY``
   (or ``DREAM_BACKEND=openai``). Messages leave the machine.
2. ``ollama`` — a local Ollama server configured with ``OLLAMA_HOST``
   (or ``DREAM_BACKEND=ollama``). Messages never leave the machine.
3. ``byok`` — bring your own key/endpoint: ``OPENAI_BASE_URL`` points at a
   user-chosen server (with ``DREAM_BACKEND=openai`` or a key). Messages
   leave the machine to that server.
4. ``echo`` — the deterministic offline backend. Nothing leaves the machine.

Every resolved route carries a sentence (English and Persian) that states
whether data leaves the machine, so ``dream --route`` / ``/route`` can never
hand-wave the privacy question.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

OFFICIAL_BASE_URLS = ("https://api.openai.com/v1", "https://api.openai.com/v1/")


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
    hosted → Ollama → BYOK → echo applies. The result is deterministic and
    offline-testable.
    """
    explicit = _env("DREAM_BACKEND").lower()
    if explicit == "openai":
        return _HOSTED if _is_official_base(_env("OPENAI_BASE_URL")) else _BYOK
    if explicit == "ollama":
        return _OLLAMA
    if explicit == "echo":
        return _ECHO

    key = _env("OPENAI_API_KEY")
    if key:
        return _HOSTED if _is_official_base(_env("OPENAI_BASE_URL")) else _BYOK
    if _env("OLLAMA_HOST"):
        return _OLLAMA
    if _env("OPENAI_BASE_URL"):
        return _BYOK
    return _ECHO


def _is_official_base(base_url: str) -> bool:
    """True when the endpoint is the official OpenAI-compatible host."""
    if not base_url:
        return True  # empty means the official default
    return base_url in OFFICIAL_BASE_URLS


# Maps a route name to the backend name ``build_backend`` understands.
_ROUTE_BACKEND: dict[str, str] = {
    "hosted": "openai",
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

