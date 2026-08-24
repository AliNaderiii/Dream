"""Sanitization for model-visible text from untrusted sources (L6, SEC-G-15).

MCP tool/resource descriptions are written by servers Dream does not
control and are shown to the model — an instruction channel. Stage C
strips the invisible layer (zero-width, bidi overrides, other control
characters), collapses whitespace runs, and caps length. Stage D layers
injection-pattern detection on top of this module; nothing untrusted
reaches a prompt without passing through here first.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["DEFAULT_VISIBLE_LIMIT", "sanitize_model_visible"]

#: Characters that carry no displayable meaning and exist in descriptions
#: only to hide directives from a human reviewer.
_INVISIBLE_RE = re.compile(
    "["
    "\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff"
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u00ad"
    "\u206a\u206b\u206c\u206d\u206e\u206f"
    "\u180e\u034f\u061c\u1806"
    "]"
)

#: C0/C1 control characters except the whitespace trio tab/LF/CR.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

#: Three or more consecutive newlines collapse to a paragraph break.
_NEWLINE_RUN_RE = re.compile(r"\n{3,}")

#: Spaces/tabs beyond a pair are cosmetic noise at best, padding at worst.
_SPACE_RUN_RE = re.compile(r"[ \t]{3,}")

DEFAULT_VISIBLE_LIMIT = 1000
_TRUNCATION_MARKER = " \u2026[truncated]"


def sanitize_model_visible(text: str, *, limit: int = DEFAULT_VISIBLE_LIMIT) -> str:
    """Return *text* with invisible characters removed and length bounded.

    Benign text survives byte-identical; the function never raises. This is
    a hygiene layer, not a verdict: stripped content is not proof of
    malice, and clean-looking text is not proof of safety.
    """
    if not isinstance(text, str):
        text = str(text)
    cleaned = unicodedata.normalize("NFC", text)
    cleaned = _INVISIBLE_RE.sub("", cleaned)
    cleaned = _CONTROL_RE.sub(" ", cleaned)
    cleaned = _NEWLINE_RUN_RE.sub("\n\n", cleaned)
    cleaned = _SPACE_RUN_RE.sub("  ", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > limit:
        cleaned = cleaned[: max(0, limit - len(_TRUNCATION_MARKER))] + _TRUNCATION_MARKER
    return cleaned
