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

from dream.normalization import normalize_importance, normalize_kind

__all__ = [
    "MIN_MESSAGE_LENGTH",
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

_EXTRACTION_PROMPT = (
    "تو یک استخراج‌کننده واقعیت هستی. فقط واقعیت‌های ماندگار درباره کاربر را "
    "که ماه آینده هم درست خواهند بود استخراج کن: نام، کار، پروژه‌ها، ابزارها، "
    "ترجیحات، محدودیت‌ها و تصمیم‌ها.\n"
    "خروجی باید فقط یک آرایه JSON باشد. اگر واقعیت ماندگاری وجود ندارد، یک آرایه "
    "خالی [] برگردان. هر عنصر آرایه باید شامل سه کلید باشد: content (متن واقعیت)، "
    "kind (یکی از semantic، episodic، procedural) و importance (عددی بین 0.0 و 1.0).\n\n"
    "مثال‌ها:\n\n"
    "کاربر: «سلام، چطوری؟»\n"
    "خروجی:\n"
    "[]\n\n"
    "کاربر: «من علی هستم و روی استارتاپ فین‌تک کار می‌کنم.»\n"
    "خروجی:\n"
    '[{"content": "کاربر علی نام دارد", "kind": "semantic", "importance": 0.9}, '
    '{"content": "کاربر روی استارتاپ فین‌تک کار می‌کند", "kind": "semantic", "importance": 0.9}]\n\n'
    "کاربر: «من همیشه از پایتون برای برنامه‌نویسی استفاده می‌کنم.»\n"
    "خروجی:\n"
    '[{"content": "کاربر همیشه از پایتون برای برنامه‌نویسی استفاده می‌کند", '
    '"kind": "semantic", "importance": 0.8}]\n\n'
    "کاربر: «فردا جلسه مهمی با تیم طراحی دارم.»\n"
    "خروجی:\n"
    '[{"content": "کاربر فردا جلسه مهمی با تیم طراحی دارد", "kind": "episodic", "importance": 0.7}]'
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


def extract_facts(
    backend: Any, user_message: str, env: dict[str, str] | None = None
) -> ExtractionResult:
    """Extract durable facts from a user message in a separate model pass.

    Never sends any assistant reply to the model. Uses no tools. Uses
    defensive raw JSON decoding to tolerate prose wrappers or formatting
    artifacts.
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
        kind = normalize_kind(item.get("kind", "semantic"))
        importance = normalize_importance(item.get("importance", 0.5))
        facts.append(ExtractedFact(content=content, kind=kind, importance=importance))

    if not facts:
        return ExtractionResult(facts=[], status=STATUS_NO_FACTS, raw_text=raw_text)

    return ExtractionResult(facts=facts, status=STATUS_FACTS_FOUND, raw_text=raw_text)
