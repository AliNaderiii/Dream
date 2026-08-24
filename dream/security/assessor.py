"""Auxiliary risk assessor for dangerous commands (layer L2, SEC-G-04).

The assessor is a cheap secondary classification step that runs BEFORE a
human is asked (``smart`` mode) or as the sole classifier when no model
backend is available. It never replaces the L3 floor — the floor has
already run by the time this module is consulted — and it never approves
anything by itself in ``manual`` mode; it only orders the question.

Discipline (pinned by tests):

* Strict response schema: exactly ``{"level": <low|medium|high|
  catastrophic>, "reason": <non-empty string>}`` as JSON. Any deviation —
  non-JSON, missing keys, extra keys, wrong types, unknown level — is a
  denial. The assessor is fail-closed.
* Hard timeout: the model call runs in a worker thread joined with a hard
  deadline. A hung backend yields a denial, never an indefinite wait.
* Error isolation: any exception raised by the backend is a denial.
* Offline-first: with ``model_call=None`` (echo backend, offline mode, no
  provider configured) only the deterministic pattern rules run. No test
  and no offline path ever touches the network.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from dream.security.blocklist import scan

__all__ = [
    "ASSESS_TIMEOUT_SECONDS",
    "Assessment",
    "RISK_LEVELS",
    "assess",
    "pattern_assess",
]

RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high", "catastrophic")

#: Default hard deadline for one assessor model call, in seconds. The
#: classification is advisory bookkeeping; it must never outrun the turn.
ASSESS_TIMEOUT_SECONDS = 5.0

Verdict = Literal["allow_once", "prompt", "deny"]

#: Strict prompt: one JSON object, no prose. The schema is repeated verbatim
#: so a small model can copy it; the refusal behaviour on any other shape is
#: enforced by the parser, not by the model's goodwill.
ASSESS_PROMPT = (
    "You classify one shell command for a security gate. Reply with exactly "
    'one JSON object and nothing else, shaped {"level": "low"|"medium"|'
    '"high"|"catastrophic", "reason": "<one short sentence>"}. '
    "low = read-only inspection; medium = bounded local change; "
    "high = destructive or privileged change; catastrophic = irreversible "
    "system-wide damage. Command:\n"
)


@dataclass(frozen=True)
class Assessment:
    """The assessor's verdict and why it was reached.

    ``level`` is ``None`` when no classification could be produced
    (timeout, backend error, schema violation); such assessments always
    carry ``verdict == "deny"``.
    """

    level: str | None
    verdict: Verdict
    reason_en: str
    reason_fa: str
    source: str  # "pattern" | "model" | "model_timeout" | "model_error" | "schema_violation"


_LEVEL_TO_VERDICT: dict[str, Verdict] = {
    "low": "allow_once",
    "medium": "prompt",
    "high": "prompt",
    "catastrophic": "deny",
}

_DENY_REASONS = {
    "model_timeout": (
        "risk assessment timed out; denied by default",
        "\u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u0631\u06cc\u0633\u06a9 "
        "\u0628\u0647\u200c\u0645\u0648\u0642\u0639 "
        "\u0645\u062a\u0648\u0642\u0641 \u0634\u062f\u061b \u0628\u0647\u200c\u0637\u0648\u0631 "
        "\u067e\u06cc\u0634\u200c\u0641\u0631\u0636 "
        "\u0631\u062f \u0634\u062f",
    ),
    "model_error": (
        "risk assessment failed; denied by default",
        "\u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u0631\u06cc\u0633\u06a9 "
        "\u0646\u0627\u0645\u0648\u0641\u0642 \u0628\u0648\u062f\u061b "
        "\u0628\u0647\u200c\u0637\u0648\u0631 \u067e\u06cc\u0634\u200c\u0641\u0631\u0636 "
        "\u0631\u062f \u0634\u062f",
    ),
    "schema_violation": (
        "risk assessment returned an invalid shape; denied by default",
        "\u062e\u0631\u0648\u062c\u06cc \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc "
        "\u0631\u06cc\u0633\u06a9 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 "
        "\u0628\u0648\u062f\u061b \u0628\u0647\u200c\u0637\u0648\u0631 "
        "\u067e\u06cc\u0634\u200c\u0641\u0631\u0636 \u0631\u062f \u0634\u062f",
    ),
}


def _deny(source: str) -> Assessment:
    reason_en, reason_fa = _DENY_REASONS[source]
    return Assessment(
        level=None, verdict="deny", reason_en=reason_en, reason_fa=reason_fa, source=source
    )


_LEVEL_NAME_FA = {
    "low": "\u06a9\u0645",
    "medium": "\u0645\u062a\u0648\u0633\u0637",
    "high": "\u0632\u06cc\u0627\u062f",
    "catastrophic": "\u0641\u0627\u062c\u0639\u0647",
}


def _from_level(level: str, reason: str, source: str) -> Assessment:
    verdict = _LEVEL_TO_VERDICT[level]
    reason_fa = "\u0633\u0637\u062d \u0631\u06cc\u0633\u06a9: " + _LEVEL_NAME_FA[level]
    return Assessment(
        level=level,
        verdict=verdict,
        reason_en=reason or level,
        reason_fa=reason_fa,
        source=source,
    )


# --------------------------------------------------------------------------- #
# Deterministic pattern rules (offline / echo path — no network, ever)
# --------------------------------------------------------------------------- #

_HIGH_VERBS = frozenset(
    {"rm", "dd", "mkfs", "fdisk", "parted", "shutdown", "reboot", "halt", "poweroff", "iptables"}
)
_MEDIUM_VERBS = frozenset(
    {
        "mv",
        "cp",
        "mkdir",
        "touch",
        "pip",
        "pip3",
        "npm",
        "npx",
        "yarn",
        "sed",
        "awk",
        "curl",
        "wget",
        "git",
        "kill",
        "chmod",
        "chown",
        "tar",
        "unzip",
    }
)
_GIT_WRITE_SUBCOMMANDS = frozenset(
    {
        "push",
        "commit",
        "add",
        "merge",
        "rebase",
        "reset",
        "rm",
        "mv",
        "checkout",
        "switch",
        "tag",
        "cherry-pick",
        "apply",
        "clean",
    }
)

_LOW_VERBS = frozenset(
    {
        "ls",
        "dir",
        "cat",
        "type",
        "echo",
        "printf",
        "pwd",
        "date",
        "grep",
        "egrep",
        "head",
        "tail",
        "wc",
        "which",
        "where",
        "file",
        "stat",
        "env",
        "whoami",
        "hostname",
        "uname",
        "true",
        "cd",
    }
)


def _verb_of(command: str) -> str:
    tokens = [token for token in command.split() if token]
    index = 0
    while index < len(tokens) and tokens[index] in ("sudo", "doas", "env"):
        index += 1
    if index >= len(tokens):
        return ""
    verb = tokens[index].rsplit("/", 1)[-1].lower()
    if verb == "git" and index + 1 < len(tokens):
        verb = f"git {tokens[index + 1].lower()}"
    return verb


def pattern_assess(command: str) -> Assessment:
    """Classify by deterministic verb rules only. Offline-safe by design."""
    if scan(command) is not None:
        return _from_level(
            "catastrophic",
            "command matches the security floor",
            "pattern",
        )
    verb = _verb_of(command)
    lowered = command.lower()
    if "sudo" in lowered.split() or "doas" in lowered.split():
        return _from_level("high", "privilege escalation requested", "pattern")
    if verb == "rm":
        return _from_level("high", "recursive or forced deletion", "pattern")
    if verb in _HIGH_VERBS:
        return _from_level("high", f"high-risk verb: {verb}", "pattern")
    if verb == "git push" and ("--force" in lowered or " -f" in f" {lowered} "):
        return _from_level("high", "force push rewrites shared history", "pattern")
    if verb in _MEDIUM_VERBS or ">" in command or ">>" in command:
        return _from_level("medium", f"bounded change: {verb or 'redirect'}", "pattern")
    if verb.startswith("git ") and verb.split(" ", 1)[1] in _GIT_WRITE_SUBCOMMANDS:
        return _from_level("medium", f"repository write: {verb}", "pattern")
    if verb in _LOW_VERBS or verb.startswith("git "):
        return _from_level("low", f"read-only inspection: {verb}", "pattern")
    # Unknown verbs fail toward the human: medium prompts rather than runs.
    return _from_level("medium", "unrecognised command; asking a human", "pattern")


# --------------------------------------------------------------------------- #
# Model-backed assessment (strict schema, hard timeout, fail closed)
# --------------------------------------------------------------------------- #


def _parse_model_reply(reply: str) -> Assessment | None:
    try:
        payload = json.loads(reply)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"level", "reason"}:
        return None
    level = payload["level"]
    reason = payload["reason"]
    if level not in RISK_LEVELS or not isinstance(reason, str) or not reason.strip():
        return None
    return _from_level(level, reason.strip(), "model")


def assess(
    command: str,
    *,
    model_call: Callable[[str], str] | None = None,
    timeout: float = ASSESS_TIMEOUT_SECONDS,
) -> Assessment:
    """Classify *command*; with ``model_call`` via the backend, else patterns.

    ``model_call`` is a ``Callable[[str], str]`` that turns a prompt into one
    completion. It runs in a daemon worker thread joined with ``timeout``; a
    backend that hangs is abandoned and the verdict is a denial. Any
    exception the backend raises is equally a denial.
    """
    if model_call is None:
        return pattern_assess(command)
    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["reply"] = model_call(ASSESS_PROMPT + command)
        except BaseException as exc:  # noqa: BLE001 — isolation is the point
            box["error"] = exc

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return _deny("model_timeout")
    if "error" in box:
        return _deny("model_error")
    parsed = _parse_model_reply(str(box.get("reply", "")))
    if parsed is None:
        return _deny("schema_violation")
    return parsed
