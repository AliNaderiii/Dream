"""SKILL.md format: agentskills.io frontmatter plus Dream house rules.

A v2 skill is a directory containing ``SKILL.md``: YAML frontmatter with
``name`` and ``description``, then a markdown body.  This module is the
strict parser.  An invalid file is a per-skill error, never a crash.

House rules on top of the public spec (documented in MEM-C.md):

* ``description`` is capped at :data:`DESCRIPTION_MAX_CHARS` (60), tighter
  than the spec's 1024, so the catalog of name+description stays cheap.
* Frontmatter is a flat ``key: value`` map parsed with the standard
  library — no YAML runtime dependency in ``dream/``.
* Every error is bilingual (Persian first) and names the field that failed.

Authoring templates (English and Persian) live here as constants so they
ship with the package and can be pinned by test without extra data files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from dream.memory import normalize_fa

# Dream house cap. The public spec allows 1024; the catalog budget is why
# this runtime is stricter. Gloss: توضیح مهارت حداکثر ۶۰ نویسه است.
DESCRIPTION_MAX_CHARS = 60
NAME_MAX_CHARS = 64

# agentskills.io name: lowercase letters, digits, hyphens; no leading,
# trailing, or consecutive hyphens.
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*)\r?\n---[ \t]*(?:\r?\n(.*))?\Z",
    re.DOTALL,
)
_SCALAR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_STEP_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")

# Optional keys accepted and ignored by this runtime (spec-compatible).
_OPTIONAL_KEYS = frozenset({"license", "compatibility", "metadata", "allowed-tools"})


class SkillFormatError(ValueError):
    """A SKILL.md failed strict validation. Bilingual ``args[0]``."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details)


# Gloss: «فایل SKILL.md باید با پیشانی YAML بین --- شروع شود.»
_ERR_FRONTMATTER_FA = (
    "\u0641\u0627\u06cc\u0644 SKILL.md \u0628\u0627\u06cc\u062f \u0628\u0627 "
    "\u067e\u06cc\u0634\u0627\u0646\u06cc YAML \u0628\u06cc\u0646 --- "
    "\u0634\u0631\u0648\u0639 \u0634\u0648\u062f."
)
_ERR_FRONTMATTER_EN = " SKILL.md must start with a YAML frontmatter block delimited by ---."

# Gloss: «پیشانی YAML نامعتبر است؛ فقط جفت‌های key: value در یک سطر پذیرفته می‌شود.»
_ERR_YAML_FA = (
    "\u067e\u06cc\u0634\u0627\u0646\u06cc YAML \u0646\u0627\u0645\u0639\u062a\u0628\u0631 "
    "\u0627\u0633\u062a\u061b \u0641\u0642\u0637 \u062c\u0641\u062a\u200c\u0647\u0627\u06cc "
    "key: value \u062f\u0631 \u06cc\u06a9 \u0633\u0637\u0631 \u067e\u0630\u06cc\u0631\u0641\u062a"
    "\u0647 "
    "\u0645\u06cc\u200c\u0634\u0648\u062f."
)
_ERR_YAML_EN = " Frontmatter is invalid; only single-line key: value pairs are accepted."

# Gloss: «فیلد name الزامی است.»
_ERR_NAME_MISSING_FA = (
    "\u0641\u06cc\u0644\u062f name \u0627\u0644\u0632\u0627\u0645\u06cc \u0627\u0633\u062a."
)
_ERR_NAME_MISSING_EN = " The name field is required."

# Gloss: «نام مهارت نامعتبر است: فقط حروف کوچک لاتین، رقم و خط تیره؛ حداکثر ۶۴ نویسه؛ بدون --.»
_ERR_NAME_FA = (
    "\u0646\u0627\u0645 \u0645\u0647\u0627\u0631\u062a \u0646\u0627\u0645\u0639\u062a\u0628\u0631 "
    "\u0627\u0633\u062a: \u0641\u0642\u0637 \u062d\u0631\u0648\u0641 \u06a9\u0648\u0686\u06a9 "
    "\u0644\u0627\u062a\u06cc\u0646\u060c \u0631\u0642\u0645 \u0648 \u062e\u0637 \u062a\u06cc"
    "\u0631\u0647\u061b "
    "\u062d\u062f\u0627\u06a9\u062b\u0631 \u06f6\u06f4 \u0646\u0648\u06cc\u0633\u0647\u061b "
    "\u0628\u062f\u0648\u0646 --."
)
_ERR_NAME_EN = (
    " Skill name is invalid: lowercase letters, digits and hyphens only;"
    " at most 64 characters; no leading, trailing, or consecutive hyphens."
)

# Gloss: «نام مهارت باید با نام پوشه یکی باشد ({folder} در برابر {name}).»
_ERR_FOLDER_FA = (
    "\u0646\u0627\u0645 \u0645\u0647\u0627\u0631\u062a \u0628\u0627\u06cc\u062f \u0628\u0627 "
    "\u0646\u0627\u0645 \u067e\u0648\u0634\u0647 \u06cc\u06a9\u06cc \u0628\u0627\u0634\u062f "
    "({folder} \u062f\u0631 \u0628\u0631\u0627\u0628\u0631 {name})."
)
_ERR_FOLDER_EN = " Skill name must match the parent folder name ({folder!r} vs {name!r})."

# Gloss: «فیلد description الزامی است.»
_ERR_DESC_MISSING_FA = (
    "\u0641\u06cc\u0644\u062f description \u0627\u0644\u0632\u0627\u0645\u06cc \u0627\u0633\u062a."
)
_ERR_DESC_MISSING_EN = " The description field is required."

# Gloss: «توضیح مهارت باید حداکثر ۶۰ نویسه باشد (الان {n}). کوتاه‌تر بنویس.»
_ERR_DESC_LEN_FA = (
    "\u062a\u0648\u0636\u06cc\u062d \u0645\u0647\u0627\u0631\u062a \u0628\u0627\u06cc\u062f "
    "\u062d\u062f\u0627\u06a9\u062b\u0631 \u06f6\u06f0 \u0646\u0648\u06cc\u0633\u0647 \u0628"
    "\u0627\u0634\u062f "
    "(\u0627\u0644\u0627\u0646 {n}). \u06a9\u0648\u062a\u0627\u0647\u200c\u062a\u0631 \u0628"
    "\u0646\u0648\u06cc\u0633."
)
_ERR_DESC_LEN_EN = (
    " Skill description must be at most {max} characters (got {n})."
    " Shorten it so the catalog stays cheap."
)

# Gloss: «بدنهٔ markdown خالی است؛ مهارت باید دستورالعمل داشته باشد.»
_ERR_BODY_FA = (
    "\u0628\u062f\u0646\u0647\u0654 markdown \u062e\u0627\u0644\u06cc \u0627\u0633\u062a\u061b "
    "\u0645\u0647\u0627\u0631\u062a \u0628\u0627\u06cc\u062f \u062f\u0633\u062a\u0648\u0631\u0627"
    "\u0644\u0639\u0645\u0644 "
    "\u062f\u0627\u0634\u062a\u0647 \u0628\u0627\u0634\u062f."
)
_ERR_BODY_EN = " Markdown body is empty; a skill must include instructions."


def validate_skill_name(name: str) -> str:
    """Return a spec-legal skill name or raise :class:`SkillFormatError`."""
    cleaned = name.strip()
    if (
        not cleaned
        or len(cleaned) > NAME_MAX_CHARS
        or not _NAME_RE.match(cleaned)
    ):
        raise SkillFormatError(_ERR_NAME_FA + _ERR_NAME_EN, name=name)
    return cleaned


def validate_description(description: str) -> str:
    """Return a house-legal description or raise :class:`SkillFormatError`."""
    cleaned = description.strip()
    if not cleaned:
        raise SkillFormatError(_ERR_DESC_MISSING_FA + _ERR_DESC_MISSING_EN)
    if len(cleaned) > DESCRIPTION_MAX_CHARS:
        raise SkillFormatError(
            _ERR_DESC_LEN_FA.format(n=len(cleaned))
            + _ERR_DESC_LEN_EN.format(max=DESCRIPTION_MAX_CHARS, n=len(cleaned)),
            length=len(cleaned),
            limit=DESCRIPTION_MAX_CHARS,
        )
    return cleaned


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split ``SKILL.md`` text into ``(fields, body)``.

    Only flat ``key: value`` lines are accepted.  Indented continuation
    (a nested ``metadata:`` map) is ignored so optional spec fields do
    not fail a skill.  Anything else is a format error.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise SkillFormatError(_ERR_FRONTMATTER_FA + _ERR_FRONTMATTER_EN)
    raw_head, raw_body = match.group(1), match.group(2) or ""
    fields: dict[str, str] = {}
    for raw_line in raw_head.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line[:1] in {" ", "\t"}:
            # Nested optional block (metadata:); skip, do not fail.
            continue
        parsed = _SCALAR_RE.match(line.strip())
        if not parsed:
            raise SkillFormatError(_ERR_YAML_FA + _ERR_YAML_EN, line=line)
        key, value = parsed.group(1), _unquote(parsed.group(2))
        fields[key] = value
    return fields, raw_body.lstrip("\n")


def extract_steps(body: str) -> tuple[str, ...]:
    """Pull markdown list items out of a body, if any.

    Progressive disclosure does not require steps — the body is the
    source of truth — but v1 callers (``use_skill``) still expect a
    step tuple when the author wrote a list.
    """
    steps: list[str] = []
    for raw_line in body.splitlines():
        match = _STEP_RE.match(raw_line.strip())
        if match:
            steps.append(match.group(1).strip())
    return tuple(steps)


@dataclass(frozen=True, slots=True)
class SkillDocument:
    """A validated SKILL.md: name, description, body, derived steps."""

    name: str
    description: str
    body: str
    steps: tuple[str, ...]
    extras: tuple[tuple[str, str], ...] = ()


def parse_skill_md(text: str, *, folder: str | None = None) -> SkillDocument:
    """Parse and strictly validate one ``SKILL.md`` document."""
    fields, body = parse_frontmatter(text)
    if "name" not in fields or not str(fields["name"]).strip():
        raise SkillFormatError(_ERR_NAME_MISSING_FA + _ERR_NAME_MISSING_EN)
    name = validate_skill_name(fields["name"])
    if folder is not None and folder != name:
        raise SkillFormatError(
            _ERR_FOLDER_FA.format(folder=folder, name=name)
            + _ERR_FOLDER_EN.format(folder=folder, name=name),
            folder=folder,
            name=name,
        )
    if "description" not in fields:
        raise SkillFormatError(_ERR_DESC_MISSING_FA + _ERR_DESC_MISSING_EN)
    description = validate_description(fields["description"])
    body = body.strip()
    if not body:
        raise SkillFormatError(_ERR_BODY_FA + _ERR_BODY_EN)
    extras = tuple(
        (key, value)
        for key, value in fields.items()
        if key not in {"name", "description"}
    )
    return SkillDocument(
        name=name,
        description=description,
        body=body,
        steps=extract_steps(body),
        extras=extras,
    )


def render_skill_md(name: str, description: str, body: str) -> str:
    """Render a canonical SKILL.md (Latin labels, Dream house rules)."""
    name = validate_skill_name(name)
    description = validate_description(description)
    body = body.strip()
    if not body:
        raise SkillFormatError(_ERR_BODY_FA + _ERR_BODY_EN)
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"


def slash_from_legacy_name(name: str) -> str:
    """Turn a v1 (possibly Persian) skill name into one slash token.

    Spaces become hyphens after the shared normalizer so ``/tea-brew``
    and ``/\u0686\u0627\u06cc-\u062f\u0645-\u06a9\u0631\u062f\u0646`` are
    single tokens.  Unsafe leftover characters are dropped.
    """
    folded = normalize_fa(name).strip()
    pieces = [part for part in re.split(r"\s+", folded) if part]
    slug = "-".join(pieces)
    slug = re.sub(r"[^0-9A-Za-z\u0600-\u06FF-]+", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug.lower() if slug.isascii() else slug


# Standard section order used by both templates and the /learn pipeline
# (Stage D). Do not invent commands in a template.
TEMPLATE_SECTIONS: tuple[str, ...] = (
    "Purpose",
    "When to use",
    "Instructions",
    "Examples",
    "Guardrails",
)

TEMPLATE_EN = """---
name: example-skill
description: Short what-and-when line, at most 60 chars.
---

# example-skill

## Purpose

One paragraph on what this skill does. Do not invent tools or commands.

## When to use

Triggers, file types, and phrases that should load this skill.

## Instructions

1. First concrete step
2. Second concrete step
3. How to finish and what to report

## Examples

- Input: a typical request
- Output: the shape of a good result

## Guardrails

- Do not run dangerous tools unless the owner approved them
- Do not overwrite another skill; edit creates a new version
"""

# Persian template: same section order, Persian headings. Name stays
# hyphen-case (spec). Description is Persian and <= 60 chars.
# Gloss of description: «الگوی فارسی مهارت؛ چه می‌کند و کی به کار می‌آید.»
TEMPLATE_FA = (
    "---\n"
    "name: nemune-maharat\n"
    "description: "
    "\u0627\u0644\u06af\u0648\u06cc \u0641\u0627\u0631\u0633\u06cc \u0645\u0647\u0627\u0631\u062a"
    "\u061b "
    "\u0686\u0647 \u0645\u06cc\u200c\u06a9\u0646\u062f \u0648 \u06a9\u06cc \u0628\u0647 \u06a9"
    "\u0627\u0631 "
    "\u0645\u06cc\u200c\u0622\u06cc\u062f.\n"
    "---\n"
    "\n"
    "# nemune-maharat\n"
    "\n"
    "## "
    "\u0647\u062f\u0641\n"  # هدف
    "\n"
    "\u06cc\u06a9 \u067e\u0627\u0631\u0627\u06af\u0631\u0627\u0641 \u062f\u0631\u0628\u0627\u0631"
    "\u0647 "
    "\u06a9\u0627\u0631\u06cc \u06a9\u0647 \u0627\u06cc\u0646 \u0645\u0647\u0627\u0631\u062a "
    "\u0627\u0646\u062c\u0627\u0645 "
    "\u0645\u06cc\u200c\u062f\u0647\u062f. \u0627\u0628\u0632\u0627\u0631 \u06cc\u0627 \u062f"
    "\u0633\u062a\u0648\u0631 "
    "\u062a\u0627\u0632\u0647 \u0646\u0633\u0627\u0632.\n"
    "\n"
    "## "
    # Gloss: when to use
    "\u0686\u0647 \u0632\u0645\u0627\u0646\u06cc \u0628\u0647 \u06a9\u0627\u0631 \u0628\u0631"
    "\u0648\n"
    "\n"
    "\u0634\u0631\u0627\u06cc\u0637\u060c \u0646\u0648\u0639 \u0641\u0627\u06cc\u0644 \u0648 "
    "\u0639\u0628\u0627\u0631\u062a\u200c\u0647\u0627\u06cc\u06cc \u06a9\u0647 \u0628\u0627\u06cc"
    "\u062f \u0627\u06cc\u0646 "
    "\u0645\u0647\u0627\u0631\u062a \u0631\u0627 \u0628\u0627\u0631 \u06a9\u0646\u0646\u062f.\n"
    "\n"
    "## "
    "\u062f\u0633\u062a\u0648\u0631\u0627\u0644\u0639\u0645\u0644\n"  # دستورالعمل
    "\n"
    "1. \u0642\u062f\u0645 \u0627\u0648\u0644\n"
    "2. \u0642\u062f\u0645 \u062f\u0648\u0645\n"
    "3. \u0686\u06af\u0648\u0646\u0647 \u062a\u0645\u0627\u0645 \u06a9\u0646 \u0648 \u0686\u0647 "
    "\u06af\u0632\u0627\u0631\u0634 "
    "\u0628\u062f\u0647\n"
    "\n"
    "## "
    "\u0646\u0645\u0648\u0646\u0647\u200c\u0647\u0627\n"  # نمونه‌ها
    "\n"
    "- \u0648\u0631\u0648\u062f\u06cc: \u06cc\u06a9 \u062f\u0631\u062e\u0648\u0627\u0633\u062a "
    "\u0645\u0639\u0645\u0648\u0644\n"
    "- \u062e\u0631\u0648\u062c\u06cc: \u0634\u06a9\u0644 \u06cc\u06a9 \u067e\u0627\u0633\u062e "
    "\u062e\u0648\u0628\n"
    "\n"
    "## "
    "\u062d\u062f\u0648\u062f\n"  # حدود
    "\n"
    "- \u0627\u0628\u0632\u0627\u0631 \u062e\u0637\u0631\u0646\u0627\u06a9 \u0631\u0627 \u0628"
    "\u062f\u0648\u0646 "
    "\u062a\u0623\u06cc\u06cc\u062f \u0635\u0627\u062d\u0628 \u0627\u062c\u0631\u0627 \u0646"
    "\u06a9\u0646\n"
    "- \u0645\u0647\u0627\u0631\u062a \u062f\u06cc\u06af\u0631 \u0631\u0627 \u0631\u0648\u06cc"
    "\u200c\u0646\u0648\u06cc\u0633 "
    "\u0646\u06a9\u0646\u061b \u0648\u06cc\u0631\u0627\u06cc\u0634 \u0646\u0633\u062e\u0647\u0654"
    " \u062a\u0627\u0632\u0647 "
    "\u0645\u06cc\u200c\u0633\u0627\u0632\u062f\n"
)


def authoring_templates() -> dict[str, str]:
    """English and Persian SKILL.md authoring templates."""
    return {"en": TEMPLATE_EN, "fa": TEMPLATE_FA}
