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

__all__ = ["DEFAULT_VISIBLE_LIMIT", "sanitize_model_visible", "strip_invisible"]

#: Characters that carry no displayable meaning and exist in descriptions
#: only to hide directives from a human reviewer. NOTE: U+200C (ZWNJ) is
#: deliberately NOT listed — it is first-class Persian orthography
#: (``می‌خواهم``, ``دستورالعمل‌ها``) and flagging it would break every
#: legitimate Persian text. Directional MARKS (LRM/RLM) are likewise kept:
#: mixed-direction text uses them honestly; only overrides/isolates go.
_INVISIBLE_RE = re.compile(
    "["
    "\u200b\u200d\u2060\u2061\u2062\u2063\u2064\ufeff"
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


def strip_invisible(text: str) -> str:
    """Remove invisible/control characters without collapsing or capping.

    This is the L5 strip layer: hidden Unicode (zero-width, bidi overrides,
    soft hyphens, Mongolian vowel separators, tag-adjacent controls) cannot
    carry meaning in untrusted text, so they go. Visible text, newlines, and
    tabs survive byte-identical.
    """
    if not isinstance(text, str):
        text = str(text)
    cleaned = unicodedata.normalize("NFC", text)
    cleaned = _INVISIBLE_RE.sub("", cleaned)
    return _CONTROL_RE.sub(" ", cleaned)


def sanitize_model_visible(text: str, *, limit: int = DEFAULT_VISIBLE_LIMIT) -> str:
    """Return *text* with invisible characters removed and length bounded.

    Benign text survives byte-identical; the function never raises. This is
    a hygiene layer, not a verdict: stripped content is not proof of
    malice, and clean-looking text is not proof of safety.
    """
    cleaned = strip_invisible(text)
    cleaned = _NEWLINE_RUN_RE.sub("\n\n", cleaned)
    cleaned = _SPACE_RUN_RE.sub("  ", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > limit:
        cleaned = cleaned[: max(0, limit - len(_TRUNCATION_MARKER))] + _TRUNCATION_MARKER
    return cleaned
