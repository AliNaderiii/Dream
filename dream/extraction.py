"""Durable fact extraction pass for Dream.

Runs an additional model pass after the conversational reply is produced to
extract durable facts from the user's message. Never sends any assistant reply
to the model or attaches any tools.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

from dream.memory import _SYNONYM_INDEX, _stem_fa, _tokenize
from dream.normalization import normalize_importance, normalize_kind

__all__ = [
    "MIN_MESSAGE_LENGTH",
    "STATUS_ABANDONED",
    "STATUS_DISABLED",
    "STATUS_ERROR",
    "STATUS_FACTS_FOUND",
    "STATUS_NO_FACTS",
    "STATUS_TOO_SHORT",
    "STATUS_UNPARSEABLE",
    "ExtractedFact",
    "ExtractionResult",
    "extract_facts",
]

MIN_MESSAGE_LENGTH: int = 8

STATUS_FACTS_FOUND = "facts_found"
STATUS_NO_FACTS = "no_facts"
STATUS_TOO_SHORT = "too_short"
STATUS_DISABLED = "disabled"
STATUS_UNPARSEABLE = "unparseable"
STATUS_ERROR = "error"
# The pass was still running when its wall-clock budget expired. The reply
# goes out regardless; the pass itself keeps running in the background.
STATUS_ABANDONED = "abandoned"

# Generic framing, pronouns, copulas, and prepositions that extraction
# boilerplate routinely introduces. Candidate facts must share at least one
# substantive stem outside this set with the user's message.
_EXTRACTION_STOPWORDS: tuple[str, ...] = (
    # User framing
    "\u06a9\u0627\u0631\u0628\u0631",
    # Pronouns
    "\u0645\u0646",
    "\u062a\u0648",
    "\u062auto",
    "\u0645\u0627",
    "\u0634\u0645\u0627",
    "\u0627\u06cc\u0634\u0627\u0646",
    "\u0648\u06cc",
    "\u0622\u0646\u0647\u0627",
    "\u0627\u06cc\u0646\u0647\u0627",
    "\u062e\u0648\u062f",
    "\u062e\u0648\u062f\u0634",
    "\u062e\u0648\u062f\u0645",
    "\u062e\u0648\u062f\u062a",
    "\u062e\u0648\u062f\u0645\u0627\u0646",
    "\u062e\u0648\u062f\u062a\u0627\u0646",
    "\u062e\u0648\u062f\u0634\u0627\u0646",
    # Demonstratives and articles
    "\u0627\u06cc\u0646",
    "\u0622\u0646",
    "\u06cc\u06a9",
    "\u06cc\u06a9\u06cc",
    "\u0647\u0645\u06cc\u0646",
    "\u0647\u0645\u0627\u0646",
    # Prepositions
    "\u0628\u0647",
    "\u0628\u0627",
    "\u0627\u0632",
    "\u062f\u0631",
    "\u0628\u0631\u0627\u06cc",
    "\u0631\u0648\u06cc",
    "\u062a\u0627",
    "\u0628\u0631",
    "\u0628\u06cc",
    "\u0686\u0648\u0646",
    "\u0646\u0632\u062f",
    "\u067e\u06cc\u0634",
    "\u0632\u06cc\u0631",
    "\u067e\u0634\u062a",
    # Conjunctions and particles
    "\u0648",
    "\u06cc\u0627",
    "\u0631\u0627",
    "\u06a9\u0647",
    "\u0627\u0645\u0627",
    "\u0627\u06af\u0631",
    "\u0648\u0644\u06cc",
    "\u0647\u0645",
    "\u0646\u06cc\u0632",
    "\u0686\u0647",
    "\u0686\u0631\u0627",
    "\u0632\u06cc\u0631\u0627",
    "\u0628\u0644\u06a9\u0647",
    # Copulas, auxiliary verbs, and states
    "\u0627\u0633\u062a",
    "\u0647\u0633\u062a",
    "\u0647\u0633\u062a\u0646\u062f",
    "\u0647\u0633\u062a\u0645",
    "\u0647\u0633\u062a\u06cc",
    "\u0647\u0633\u062a\u06cc\u0645",
    "\u0646\u06cc\u0633\u062a",
    "\u0646\u06cc\u0633\u062a\u0646\u062f",
    "\u0646\u06cc\u0633\u062a\u0645",
    "\u0646\u06cc\u0633\u062a\u06cc",
    "\u0628\u0648\u062f",
    "\u0628\u0648\u062f\u0646\u062f",
    "\u0628\u0648\u062f\u0645",
    "\u0628\u0648\u062f\u06cc",
    "\u0634\u062f",
    "\u0634\u062f\u0646\u062f",
    "\u0634\u062f\u0645",
    "\u0634\u062f\u06cc",
    "\u0645\u06cc\u200c\u0628\u0627\u0634\u062f",
    "\u0645\u06cc\u200c\u0628\u0627\u0634\u0646\u062f",
    "\u0628\u0627\u0634\u0646\u062f",
    "\u0628\u0627\u0634\u062f",
    "\u0628\u0627\u0634\u0645",
    "\u062f\u0627\u0631\u062f",
    "\u062f\u0627\u0631\u0646\u062f",
    "\u062f\u0627\u0631\u0645",
    "\u062f\u0627\u0631\u06cc",
    "\u062f\u0627\u0634\u062a",
    "\u062f\u0627\u0634\u062a\u0646\u062f",
    "\u062f\u0627\u0634\u062a\u0647",
    "\u0645\u06cc\u200c\u06a9\u0646\u062f",
    "\u0645\u06cc\u200c\u06a9\u0646\u0646\u062f",
    "\u0645\u06cc\u200c\u06a9\u0646\u0645",
    "\u0645\u06cc\u200c\u06a9\u0646\u06cc",
    "\u06a9\u0631\u062f",
    "\u06a9\u0631\u062f\u0646\u062f",
    "\u06a9\u0631\u062f\u0647",
    "\u06a9\u0631\u062f\u0646",
    "\u0645\u06cc\u200c\u0634\u0648\u062f",
    "\u0645\u06cc\u200c\u0634\u0648\u0646\u062f",
    "\u0645\u06cc\u200c\u0634\u0648\u0645",
    "\u0645\u06cc\u200c\u0634\u0648\u06cc",
    "\u0634\u062f\u0647",
    "\u0645\u06cc\u200c\u0622\u06cc\u062f",
    "\u0645\u06cc\u200c\u0622\u06cc\u0646\u062f",
    "\u0645\u06cc\u200c\u0622\u06cc\u0645",
    "\u0622\u0645\u062f",
    "\u0622\u0645\u062f\u0647",
    "\u0645\u06cc\u200c\u0631\u0648\u062f",
    "\u0645\u06cc\u200c\u0631\u0648\u0646\u062f",
    "\u0645\u06cc\u200c\u0631\u0648\u0645",
    "\u0631\u0641\u062a",
    "\u0631\u0641\u062a\u0647",
    "\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u062f",
    "\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u0646\u062f",
    "\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u0645",
    "\u0645\u06cc\u200c\u062f\u0647\u062f",
    "\u0645\u06cc\u200c\u062f\u0647\u0646\u062f",
    "\u062f\u0627\u062f",
    "\u062f\u0627\u062f\u0647",
    "\u0645\u06cc\u200c\u06af\u06cc\u0631\u062f",
    "\u0645\u06cc\u200c\u06af\u06cc\u0631\u0646\u062f",
    "\u06af\u0631\u0641\u062a",
    "\u06af\u0631\u0641\u062a\u0647",
    # Adverbs / quantifiers
    "\u0647\u0631",
    "\u0647\u0645\u0647",
    "\u0647\u06cc\u0686",
    "\u062f\u06cc\u06af\u0631",
    "\u062e\u06cc\u0644\u06cc",
    "\u0628\u0633\u06cc\u0627\u0631",
    "\u06a9\u0645\u06cc",
    "\u0641\u0642\u0637",
    "\u062a\u0646\u0647\u0627",
)

_STOP_STEMS: frozenset[str] = frozenset(
    _stem_fa(tok) for word in _EXTRACTION_STOPWORDS for tok in _tokenize(word)
)

_EXTRACTION_PROMPT = (
    "تو یک استخراج‌کننده واقعیت هستی. فقط واقعیت‌های ماندگار درباره کاربر را "
    "که ماه آینده هم درست خواهند بود استخراج کن: نام، کار، پروژه‌ها، ابزارها، "
    "ترجیحات، محدودیت‌ها و تصمیم‌ها.\n"
    "خروجی باید فقط یک آرایه JSON باشد. اگر واقعیت ماندگاری وجود ندارد، یک آرایه "
    "خالی [] برگردان. هر عنصر آرایه باید شامل سه کلید باشد: content (متن واقعیت)، "
    "kind (یکی از semantic، episodic، procedural) و importance (عددی بین 0.0 و 1.0).\n"
    "\u0646\u0627\u0645 \u0627\u0641\u0631\u0627\u062f \u0631\u0627 \u0628\u0627 "
    "\u0647\u0645\u0627\u0646 \u0648\u0627\u0698\u0647\u200c\u0647\u0627\u06cc "
    "\u06a9\u0627\u0631\u0628\u0631 \u062d\u0641\u0638 \u06a9\u0646 \u0648 "
    "\u0646\u0627\u0645 \u062e\u0627\u0646\u0648\u0627\u062f\u06af\u06cc \u0631\u0627 "
    "\u062d\u0630\u0641 \u0646\u06a9\u0646.\n\n"
    "مثال‌ها:\n\n"
    "کاربر: «سلام، چطوری؟»\n"
    "خروجی:\n"
    "[]\n\n"
    "\u06a9\u0627\u0631\u0628\u0631: \u00ab\u0627\u0633\u0645 \u06a9\u0627\u0645\u0644 "
    "\u0645\u0646 \u0633\u0627\u0631\u0627 \u0631\u0627\u062f\u0645\u0646\u0634 "
    "\u0627\u0633\u062a.\u00bb\n"
    "\u062e\u0631\u0648\u062c\u06cc:\n"
    '[{"content": "\u06a9\u0627\u0631\u0628\u0631 \u0633\u0627\u0631\u0627 '
    "\u0631\u0627\u062f\u0645\u0646\u0634 \u0646\u0627\u0645 \u062f\u0627\u0631\u062f\", "
    '"kind": "semantic", "importance": 0.9}]\n\n'
    "\u06a9\u0627\u0631\u0628\u0631: \u00ab\u0645\u0646 \u0628\u0647 "
    "\u0646\u062c\u0648\u0645 \u0639\u0644\u0627\u0642\u0647\u200c\u0645\u0646\u062f\u0645 "
    "\u0648 \u0627\u0632 \u062a\u0644\u0633\u06a9\u0648\u067e "
    "\u062f\u0627\u0628\u0633\u0648\u0646\u06cc \u0627\u0633\u062a\u0641\u0627\u062f\u0647 "
    "\u0645\u06cc\u200c\u06a9\u0646\u0645.\u00bb\n"
    "\u062e\u0631\u0648\u062c\u06cc:\n"
    '[{"content": "\u06a9\u0627\u0631\u0628\u0631 \u0628\u0647 \u0646\u062c\u0648\u0645 '
    '\u0639\u0644\u0627\u0642\u0647 \u062f\u0627\u0631\u062f", '
    '"kind": "semantic", "importance": 0.8}, '
    '{"content": "\u06a9\u0627\u0631\u0628\u0631 \u0627\u0632 \u062a\u0644\u0633\u06a9\u0648\u067e '
    "\u062f\u0627\u0628\u0633\u0648\u0646\u06cc \u0627\u0633\u062a\u0641\u0627\u062f\u0647 "
    '\u0645\u06cc\u200c\u06a9\u0646\u062f", "kind": "semantic", "importance": 0.8}]\n\n'
    "\u06a9\u0627\u0631\u0628\u0631: \u00ab\u0628\u0631\u0627\u06cc \u0646\u0642\u0627\u0634\u06cc "
    "\u0631\u0646\u06af\u200c\u0631\u0648\u063a\u0646 \u0627\u0632 "
    "\u0642\u0644\u0645\u200c\u0645\u0648\u06cc \u0628\u0627\u062f\u0628\u0632\u0646\u06cc "
    "\u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u0645\u06cc\u200c\u06a9\u0646\u0645.\u00bb\n"
    "\u062e\u0631\u0648\u062c\u06cc:\n"
    '[{"content": "\u06a9\u0627\u0631\u0628\u0631 \u0628\u0631\u0627\u06cc '
    "\u0646\u0642\u0627\u0634\u06cc \u0631\u0646\u06af\u200c\u0631\u0648\u063a\u0646 "
    "\u0627\u0632 \u0642\u0644\u0645\u200c\u0645\u0648\u06cc "
    "\u0628\u0627\u062f\u0628\u0632\u0646\u06cc \u0627\u0633\u062a\u0641\u0627\u062f\u0647 "
    '\u0645\u06cc\u200c\u06a9\u0646\u062f", "kind": "semantic", "importance": 0.8}]\n\n'
    "\u06a9\u0627\u0631\u0628\u0631: \u00ab\u0647\u0641\u062a\u0647 \u0622\u06cc\u0646\u062f\u0647 "
    "\u062f\u0631 \u06a9\u0627\u0631\u06af\u0627\u0647 \u0633\u0641\u0627\u0644\u06af\u0631\u06cc "
    "\u0634\u0631\u06a9\u062a \u0645\u06cc\u200c\u06a9\u0646\u0645.\u00bb\n"
    "\u062e\u0631\u0648\u062c\u06cc:\n"
    '[{"content": "\u06a9\u0627\u0631\u0628\u0631 \u0647\u0641\u062a\u0647 '
    "\u0622\u06cc\u0646\u062f\u0647 \u062f\u0631 \u06a9\u0627\u0631\u06af\u0627\u0647 "
    "\u0633\u0641\u0627\u0644\u06af\u0631\u06cc \u0634\u0631\u06a9\u062a "
    '\u0645\u06cc\u200c\u06a9\u0646\u062f", '
    '"kind": "episodic", "importance": 0.7}]'
)


@dataclass(slots=True)
class ExtractedFact:
    """A single durable fact extracted from a user message."""

    content: str
    kind: str = "semantic"
    importance: float = 0.5

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "kind": self.kind,
            "importance": self.importance,
            }

    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ExtractedFact):
            return (
                self.content == other.content
                and self.kind == other.kind
                and math.isclose(self.importance, other.importance, abs_tol=1e-5)
            )
        if isinstance(other, dict):
            return (
                self.content == other.get("content")
                and self.kind == other.get("kind", "semantic")
                and math.isclose(self.importance, float(other.get("importance", 0.5)), abs_tol=1e-5)
            )
        return False


@dataclass(slots=True)
class ExtractionResult:
    """Result of running the fact extraction pass on a user message."""

    facts: list[ExtractedFact]
    status: str
    raw_text: str = ""

    @property
    def ok(self) -> bool:
        return self.status == STATUS_FACTS_FOUND

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": [f.to_dict() for f in self.facts],
            "status": self.status,
            "raw_text": self.raw_text,
        }

    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()


def _is_disabled(env: dict[str, str] | None = None) -> bool:
    """Check whether extraction is disabled via environment variables."""
    mapping = env if env is not None else os.environ
    val = mapping.get("DREAM_EXTRACTION", mapping.get("DREAM-EXTRACTION", "")).strip().lower()
    return val in {"off", "0", "false", "no"}


def _is_plausible_fact_json(obj: Any) -> bool:
    """Return True if ``obj`` looks like an extracted fact structure."""
    if isinstance(obj, list):
        if len(obj) == 0:
            return True
        return any(isinstance(x, dict) and "content" in x for x in obj)
    if isinstance(obj, dict):
        if "content" in obj:
            return True
        for val in obj.values():
            if isinstance(val, list) and any(
                isinstance(x, dict) and "content" in x for x in val
            ):
                return True
    return False


def _parse_raw_json(text: str) -> Any | None:
    """Scan for the first complete JSON value in text using raw_decode."""
    if not text:
        return None
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char in ("[", "{"):
            try:
                obj, _ = decoder.raw_decode(text, idx)
                if _is_plausible_fact_json(obj):
                    return obj
            except (json.JSONDecodeError, ValueError, TypeError, RecursionError):
                continue
    return None


def _extract_items(obj: Any) -> list[dict[str, Any]]:
    """Convert a parsed JSON structure into a list of candidate dictionaries."""
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        if "content" in obj:
            return [obj]
        for val in obj.values():
            if isinstance(val, list) and all(isinstance(x, dict) for x in val):
                return val
        return [obj]
    return []


_CROSS_LANGUAGE_PAIRS: dict[str, str] = {
    "startup": "\u0627\u0633\u062a\u0627\u0631\u062a\u0627\u067e",
    "fintech": "\u0641\u06cc\u0646",
    "python": "\u067e\u0627\u06cc\u062a\u0648\u0646",
    "work": "\u06a9\u0627\u0631",
    "job": "\u0634\u063a\u0644",
    "live": "\u0632\u0646\u062f\u06af",
    "lives": "\u0632\u0646\u062f\u06af",
    "tehran": "\u062a\u0647\u0631\u0627\u0646",
    "shiraz": "\u0634\u06cc\u0631\u0627\u0632",
    "name": "\u0646\u0627\u0645",
}


def _is_grounded_fact(fact_content: str, user_message: str) -> bool:
    """Check whether a candidate fact is grounded in the user's message.

    Rejects candidate facts whose substantive subject matter appears nowhere
    in the message the model supposedly extracted them from (e.g. prompt echoes).
    """
    user_tokens = _tokenize(user_message)
    if not user_tokens:
        return False
    user_stems = {_stem_fa(t) for t in user_tokens}
    user_raw = {t.lower() for t in user_tokens}
    user_expanded = set(user_stems) | user_raw
    for s in user_stems:
        user_expanded.update(_SYNONYM_INDEX.get(s, ()))
    for raw in user_raw:
        if raw in _CROSS_LANGUAGE_PAIRS:
            pair = _CROSS_LANGUAGE_PAIRS[raw]
            user_expanded.add(pair)
            user_expanded.add(_stem_fa(pair))

    fact_tokens = _tokenize(fact_content)
    if not fact_tokens:
        return False
    fact_stems = [_stem_fa(t) for t in fact_tokens]
    fact_raw = [t.lower() for t in fact_tokens]

    substantive_stems = [s for s in fact_stems if s not in _STOP_STEMS]
    substantive_raw = [
        r for r, s in zip(fact_raw, fact_stems, strict=False) if s not in _STOP_STEMS
    ]

    if substantive_stems:
        for s, r in zip(substantive_stems, substantive_raw, strict=False):
            if s in user_expanded or r in user_expanded:
                return True
            syns = _SYNONYM_INDEX.get(s, ())
            if any(syn in user_expanded for syn in syns):
                return True
            if r in _CROSS_LANGUAGE_PAIRS and _CROSS_LANGUAGE_PAIRS[r] in user_expanded:
                return True
            if s in _CROSS_LANGUAGE_PAIRS and _CROSS_LANGUAGE_PAIRS[s] in user_expanded:
                return True
        return False

    return any(
        s in user_stems or r in user_raw for s, r in zip(fact_stems, fact_raw, strict=False)
    )


def extract_facts(
    backend: Any, user_message: str, env: dict[str, str] | None = None
) -> ExtractionResult:
    """Extract durable facts from a user message in a separate model pass.

    Never sends any assistant reply to the model. Uses no tools. Uses
    defensive raw JSON decoding to tolerate prose wrappers or formatting
    artifacts. Rejects candidate facts that originate from prompt examples
    or lack substantive grounding in the user's message.
    """
    if _is_disabled(env):
        return ExtractionResult(facts=[], status=STATUS_DISABLED, raw_text="")

    stripped = user_message.strip()
    if len(stripped) < MIN_MESSAGE_LENGTH or stripped.startswith(("/", "\\")):
        return ExtractionResult(facts=[], status=STATUS_TOO_SHORT, raw_text="")

    messages = [
        {"role": "system", "content": _EXTRACTION_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        response = backend.chat(messages)
        raw_text = ""
        if isinstance(response, dict):
            raw_text = str(response.get("content") or "")
        elif isinstance(response, str):
            raw_text = response
        else:
            raw_text = str(response or "")
    except Exception as exc:
        return ExtractionResult(facts=[], status=STATUS_ERROR, raw_text=str(exc))

    if not raw_text or raw_text.startswith("Model request failed:"):
        return ExtractionResult(facts=[], status=STATUS_ERROR, raw_text=raw_text)

    parsed = _parse_raw_json(raw_text)
    if parsed is None:
        return ExtractionResult(facts=[], status=STATUS_UNPARSEABLE, raw_text=raw_text)

    items = _extract_items(parsed)
    if not items and isinstance(parsed, list) and len(parsed) == 0:
        return ExtractionResult(facts=[], status=STATUS_NO_FACTS, raw_text=raw_text)

    facts: list[ExtractedFact] = []
    for item in items:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if not _is_grounded_fact(content, user_message):
            continue
        kind = normalize_kind(item.get("kind", "semantic"))
        importance = normalize_importance(item.get("importance", 0.5))
        facts.append(ExtractedFact(content=content, kind=kind, importance=importance))

    if not facts:
        return ExtractionResult(facts=[], status=STATUS_NO_FACTS, raw_text=raw_text)

    return ExtractionResult(facts=facts, status=STATUS_FACTS_FOUND, raw_text=raw_text)
