"""``DREAM_USER_AGENT`` override policy and the regexes that gate it.

The default User-Agent is built from the package version in
:mod:`dream.agent.prompts`; this module only handles the *override*
that the operator can set through the environment. The policy is, in
order:

* ``None`` and ``""`` mean "not configured": the default is returned
  without a log record.
* Surrounding spaces and TABs (HTTP optional whitespace) are trimmed;
  nothing else is normalised. A value that is only such whitespace is
  rejected as ``blank``.
* Any C0 control (NUL, TAB, LF, CR, ...), DEL, or C1 control left
  anywhere in the trimmed value is rejected as ``control_character``.
* A trimmed value longer than ``USER_AGENT_MAX_LENGTH`` characters is
  rejected as ``too_long``.
* A value urllib cannot encode into a header (anything outside
  ISO-8859-1) is rejected as ``unencodable`` here, instead of failing
  every request later with an opaque codec error.

A rejected value is reported through :func:`_reject_user_agent` and
replaced by the default; this module never raises.
"""

from __future__ import annotations

from dream.agent.constants import (
    USER_AGENT_MAX_LENGTH,
    USER_AGENT_PRODUCT,
    log,
)

# Characters that may never appear inside a forwarded User-Agent: every C0
# control (NUL, TAB, LF, CR, ESC, ...), DEL, and the C1 controls (NEL, CSI,
# ...). CR and LF are the header-injection vector, and ``http.client`` still
# accepts a CR/LF that is followed by a space or TAB as obsolete line folding,
# so refusing bare line breaks alone is not enough. A TAB is technically legal
# inside a field value, but it is exactly the folding whitespace such a split
# needs and never appears in an honest product token, so it is refused too.
# Only surrounding spaces and TABs (the optional whitespace HTTP itself treats
# as insignificant around a field value) are trimmed before this check, so a
# padded value is accepted while one wrapped in any other control is not.
_USER_AGENT_UNSAFE = __import__("re").compile(r"[\x00-\x1f\x7f-\x9f]")
_USER_AGENT_OWS: str = " \t"


def _reject_user_agent(reason: str, length: int) -> None:
    """Record one rejected ``DREAM_USER_AGENT`` override, safely.

    The record carries the rejection reason and the override's length and
    nothing else: an environment value can hold anything the owner pasted
    into it (a token, a URL with a key in it), so the value itself is never
    logged, not even a prefix.
    """
    log.warning(
        "user-agent override rejected: %s (length=%d); using the default",
        reason,
        length,
        extra={"user_agent_reason": reason, "user_agent_length": length},
    )


def _resolve_user_agent(raw: str | None, version: str) -> str:
    """Return a safe custom User-Agent or the versioned Dream default.

    ``raw`` is the ``DREAM_USER_AGENT`` override; ``version`` is the product
    version the default is built from. See the module docstring for the
    full policy.
    """
    default = f"{USER_AGENT_PRODUCT}/{version}"
    if raw is None or raw == "":
        return default
    value = raw.strip(_USER_AGENT_OWS)
    if not value:
        _reject_user_agent("blank", len(raw))
        return default
    if _USER_AGENT_UNSAFE.search(value) is not None:
        _reject_user_agent("control_character", len(raw))
        return default
    if len(value) > USER_AGENT_MAX_LENGTH:
        _reject_user_agent("too_long", len(raw))
        return default
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        _reject_user_agent("unencodable", len(raw))
        return default
    return value
