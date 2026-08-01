"""Shared coercion helpers for Dream.

These helpers normalize values like memory kind and importance so both the
conversational agent and the extraction pass can use a single consistent
implementation without import cycles.
"""

from __future__ import annotations

import math
from typing import Any

from dream.memory import KINDS, normalize_fa

__all__ = ["normalize_kind", "normalize_importance"]

# Small local models rarely send ``kind`` exactly as the schema enumerates it:
# expect "fact", "preference", or an empty string rather than a clean
# "semantic". Rejecting the call loses the memory entirely, which is the worst
# outcome, so synonyms map onto the closest valid kind and anything
# unrecognised falls back to semantic. A fact stored under a slightly wrong
# kind is strictly better than no fact at all.
_KIND_SYNONYMS = {
    # English synonyms
    "fact": "semantic",
    "info": "semantic",
    "preference": "semantic",
    "profile": "semantic",
    "knowledge": "semantic",
    "event": "episodic",
    "episode": "episodic",
    "experience": "episodic",
    "rule": "procedural",
    "instruction": "procedural",
    "howto": "procedural",
    "how_to": "procedural",
    "procedure": "procedural",
    # Persian synonyms (semantic)
    "معنایی": "semantic",
    "واقعیت": "semantic",
    "واقعیت_ها": "semantic",
    "واقعیت_های": "semantic",
    "ترجیح": "semantic",
    "ترجیحات": "semantic",
    "اطلاعات": "semantic",
    "پروفایل": "semantic",
    "دانش": "semantic",
    "سمانتیک": "semantic",
    "سمنتیك": "semantic",
    # Persian synonyms (episodic)
    "رویدادی": "episodic",
    "رویداد": "episodic",
    "رویدادها": "episodic",
    "رخداد": "episodic",
    "رخدادها": "episodic",
    "خاطره": "episodic",
    "خاطرات": "episodic",
    "تجربه": "episodic",
    "تجارب": "episodic",
    "اپیزودیک": "episodic",
    "اپیزودی": "episodic",
    # Persian synonyms (procedural)
    "رویه_ای": "procedural",
    "رویه‌ای": "procedural",
    "رویه": "procedural",
    "رویه‌ها": "procedural",
    "دستورالعمل": "procedural",
    "دستورالعمل_ها": "procedural",
    "قاعده": "procedural",
    "قواعد": "procedural",
    "قانون": "procedural",
    "قوانین": "procedural",
    "روش": "procedural",
    "روش_ها": "procedural",
    "پروسیجرال": "procedural",
}


def normalize_kind(value: Any) -> str:
    """Map whatever a model sends as ``kind`` onto the closest valid kind.

    Accepts English and Persian synonyms, case-insensitively, treating hyphen
    and space as underscore. Anything unrecognised, or not a string at all,
    degrades to "semantic". Never raises an exception.
    """
    try:
        if not isinstance(value, str):
            return "semantic"
        text = normalize_fa(value).strip().lower()
        text = text.replace("-", "_").replace(" ", "_")
        if text in KINDS:
            return text
        return _KIND_SYNONYMS.get(text, "semantic")
    except Exception:
        return "semantic"


def normalize_importance(value: Any) -> float:
    """Coerce ``importance`` into [0.0, 1.0], defaulting to 0.5 when unreadable.

    Accepts floats, ints and numeric strings (including Persian digits).
    Rejects booleans and NaN. Anything unusable becomes 0.5. Never raises.
    """
    try:
        if isinstance(value, bool):
            return 0.5
        if isinstance(value, str):
            value = normalize_fa(value)
        number = float(value)
        if math.isnan(number):
            return 0.5
        return max(0.0, min(1.0, number))
    except (TypeError, ValueError, OverflowError):
        return 0.5
    except Exception:
        return 0.5
