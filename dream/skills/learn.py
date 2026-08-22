"""/learn pipeline: turn a source into a skill as a normal agent turn.

There is no separate ingestion engine.  This module classifies the
source, loads what it can offline, refuses URL learning when network
tools are off, and composes a standards-guided prompt that
:meth:`Dream.run` then treats as an ordinary user turn.  The skill is
saved only through the Stage C approved write path.

Large sources are framed as knowledge-base skills: a lean SKILL.md plus
``references/`` files.  Distillation must synthesise, never copy long
passages.  Re-learning the same topic folds into the existing skill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dream import tools
from dream.skills.format import (
    DESCRIPTION_MAX_CHARS,
    TEMPLATE_SECTIONS,
    authoring_templates,
    slash_from_legacy_name,
    validate_skill_name,
)
from dream.skills.registry import find_by_name, mark_skills_dirty

# A source bigger than this is framed as a knowledge-base skill.
LARGE_SOURCE_CHARS = 4_000
MAX_SOURCE_CHARS = 80_000
MAX_FILE_BYTES = 65_536
MAX_CORPUS_FILES = 40

# Gloss: «یادگیری از نشانی اینترنتی فقط وقتی مجاز است که ابزار شبکه روشن
# باشد و دریافت تایید شود. الان شبکه خاموش است؛ از مسیر محلی، گفتگو یا
# یادداشت استفاده کن.»
_ERR_URL_OFF_FA = (
    "\u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc \u0627\u0632 \u0646\u0634\u0627"
    "\u0646\u06cc \u0627\u06cc\u0646\u062a\u0631\u0646\u062a\u06cc \u0641\u0642"
    "\u0637 \u0648\u0642\u062a\u06cc \u0645\u062c\u0627\u0632 \u0627\u0633\u062a "
    "\u06a9\u0647 \u0627\u0628\u0632\u0627\u0631 \u0634\u0628\u06a9\u0647 \u0631"
    "\u0648\u0634\u0646 \u0628\u0627\u0634\u062f \u0648 \u062f\u0631\u06cc\u0627"
    "\u0641\u062a \u062a\u0627\u06cc\u06cc\u062f \u0634\u0648\u062f. \u0627\u0644"
    "\u0627\u0646 \u0634\u0628\u06a9\u0647 \u062e\u0627\u0645\u0648\u0634 \u0627"
    "\u0633\u062a\u061b \u0627\u0632 \u0645\u0633\u06cc\u0631 \u0645\u062d\u0644"
    "\u06cc\u060c \u06af\u0641\u062a\u06af\u0648 \u06cc\u0627 \u06cc\u0627\u062f"
    "\u062f\u0627\u0634\u062a \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646."
)
_ERR_URL_OFF_EN = (
    " URL learning is allowed only when network tools are enabled and the"
    " fetch is approved. Network tools are off; use a local path, the"
    " conversation, or pasted notes."
)

# Gloss: «منبع یادگیری خالی است یا خوانده نشد.»
_ERR_EMPTY_FA = (
    "\u0645\u0646\u0628\u0639 \u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc "
    "\u062e\u0627\u0644\u06cc \u0627\u0633\u062a \u06cc\u0627 \u062e\u0648\u0627"
    "\u0646\u062f\u0647 \u0646\u0634\u062f."
)
_ERR_EMPTY_EN = " The learn source is empty or could not be read."


class LearnError(ValueError):
    """Fail-closed /learn refusal. Bilingual message."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details)


@dataclass(frozen=True, slots=True)
class LearnSource:
    """One classified /learn source, already loaded (or refused)."""

    kind: str
    topic: str
    text: str
    parts: tuple[tuple[str, str], ...] = ()
    existing: Any | None = None


def _network_on() -> bool:
    return tools._network_enabled()


def _clip(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[truncated]"


def _topic_from(text: str, fallback: str) -> str:
    words = [w for w in re.split(r"\s+", text.strip()) if w][:4]
    if not words:
        return fallback
    slug = slash_from_legacy_name(" ".join(words)) or fallback
    slug = re.sub(r"[^a-z0-9-]+", "", slug.lower()) or fallback
    try:
        return validate_skill_name(slug[:64])
    except Exception:
        return fallback


def _read_workspace_file(rel: str) -> str:
    path = tools._safe_path(rel)
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raw = raw[:MAX_FILE_BYTES]
    return raw.decode("utf-8", "replace")


def _load_path(spec: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    rel = spec.strip()
    path = tools._safe_path(rel)
    if path.is_file():
        return _clip(_read_workspace_file(rel)), ((path.name, _clip(_read_workspace_file(rel))),)
    if not path.is_dir():
        raise LearnError(_ERR_EMPTY_FA + _ERR_EMPTY_EN, path=rel)
    parts: list[tuple[str, str]] = []
    blobs: list[str] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        if child.suffix.lower() not in {".txt", ".md", ".markdown", ".rst"}:
            continue
        if len(parts) >= MAX_CORPUS_FILES:
            break
        try:
            text = child.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _clip(text, 8_000)
        name = child.stem.replace(" ", "-")[:40] or f"part-{len(parts)+1}"
        parts.append((name, text))
        blobs.append(f"# {name}\n{text}")
    if not parts:
        raise LearnError(_ERR_EMPTY_FA + _ERR_EMPTY_EN, path=rel)
    return _clip("\n\n".join(blobs)), tuple(parts)


def classify_learn(argument: str, *, history: list[dict[str, Any]] | None = None) -> LearnSource:
    """Classify and load one /learn argument.

    Kinds: ``path``, ``url``, ``conversation``, ``notes``, ``corpus``.
    """
    argument = argument.strip()
    history = history or []
    lowered = argument.lower()

    if not argument or lowered in {"conversation", "chat", "session"}:
        lines = [
            str(item.get("content", ""))
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        text = _clip("\n".join(lines))
        if not text:
            raise LearnError(_ERR_EMPTY_FA + _ERR_EMPTY_EN, kind="conversation")
        topic = _topic_from(text, "conversation-notes")
        return LearnSource("conversation", topic, text, existing=find_by_name(topic))

    if lowered.startswith(("http://", "https://")) or lowered.startswith("url "):
        address = argument[4:].strip() if lowered.startswith("url ") else argument
        if not _network_on():
            raise LearnError(_ERR_URL_OFF_FA + _ERR_URL_OFF_EN, kind="url")
        fetched = tools.read_page(address)
        if fetched == tools.NETWORK_DISABLED_MESSAGE:
            raise LearnError(_ERR_URL_OFF_FA + _ERR_URL_OFF_EN, kind="url")
        text = _clip(fetched)
        if not text:
            raise LearnError(_ERR_EMPTY_FA + _ERR_EMPTY_EN, kind="url")
        topic = _topic_from(Path(address).name or "web-source", "web-source")
        return LearnSource("url", topic, text, existing=find_by_name(topic))

    # Path if it exists under the workspace (or looks like one).
    candidate = argument.split()[0]
    try:
        probe = tools._safe_path(candidate)
    except (PermissionError, ValueError):
        probe = None
    if probe is not None and probe.exists():
        text, parts = _load_path(candidate)
        kind = "corpus" if probe.is_dir() or len(text) >= LARGE_SOURCE_CHARS else "path"
        leftover = argument[len(candidate) :].strip()
        if leftover:
            text = leftover + "\n\n" + text
        topic = _topic_from(probe.stem or leftover or "local-source", "local-source")
        return LearnSource(kind, topic, text, parts=parts, existing=find_by_name(topic))

    # Pasted notes.
    topic = _topic_from(argument, "pasted-notes")
    return LearnSource("notes", topic, _clip(argument), existing=find_by_name(topic))


def compose_learn_prompt(source: LearnSource) -> str:
    """Standards-guided prompt handed to the agent as a normal turn."""
    templates = authoring_templates()
    sections = ", ".join(TEMPLATE_SECTIONS)
    large = len(source.text) >= LARGE_SOURCE_CHARS or source.kind == "corpus"
    existing_block = ""
    if source.existing is not None:
        existing_block = (
            "\n\nExisting skill to merge into (do not create a duplicate):\n"
            f"name: {source.existing.name}\n"
            f"description: {source.existing.description}\n"
            f"{source.existing.body}\n"
        )
    kb = ""
    if large:
        kb = (
            "\nThis is a large source. Write a lean SKILL.md (core models + index) "
            "and one distilled file per topic under references/, plus glossary.md "
            "when terms were earned. Synthesise; never copy long passages.\n"
        )
    return (
        "Turn the following source into one Dream skill.\n"
        f"Use hyphen-case name {source.topic!r}. "
        f"Description at most {DESCRIPTION_MAX_CHARS} characters. "
        f"Standard sections: {sections}. Do not invent commands.\n"
        "Save with edit_skill (or save_skill_bundle for a knowledge base). "
        "If a skill of this topic already exists, fold the new material in; "
        "do not write a second skill.\n"
        f"{kb}"
        "English template shape:\n"
        f"{templates['en']}\n"
        f"{existing_block}\n"
        f"Source kind: {source.kind}\n"
        f"Source:\n{source.text}\n"
    )


def prepare_learn_turn(
    message: str, *, history: list[dict[str, Any]] | None = None
) -> str:
    """Strip the /learn prefix, load the source, return the composed turn."""
    raw = message.strip()
    if raw.startswith("\\"):
        raw = "/" + raw[1:]
    if raw.lower().startswith("/learn"):
        raw = raw[6:].strip()
    source = classify_learn(raw, history=history)
    return compose_learn_prompt(source)


def install_skill_bundle(
    name: str,
    description: str,
    body: str,
    references: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Write a SKILL.md plus optional references/ through the v2 write path.

    Merge-on-re-learn: if the skill exists, ``replace=True`` records a new
    version instead of a second name.
    """
    from dream.skills import edit_skill, save_skill_md
    from dream.skills.format import render_skill_md

    cleaned = validate_skill_name(name)
    existing = find_by_name(cleaned)
    if existing is not None:
        # Fold: keep existing body, append a merged section if new text differs.
        merged_body = body.strip()
        if existing.body.strip() and existing.body.strip() not in merged_body:
            merged_body = existing.body.strip() + "\n\n## Updates\n\n" + merged_body
        result = edit_skill(cleaned, description, merged_body)
        status = "merged"
    else:
        result = {"filename": save_skill_md(cleaned, description, body), "status": "created"}
        status = "created"
    written = [result["filename"]]
    refs = references or {}
    if refs:
        for ref_name, ref_body in refs.items():
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", ref_name).strip("-") or "note"
            rel = f"skills/{cleaned}/references/{safe}.md"
            path = tools._safe_path(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(ref_body.strip() + "\n", encoding="utf-8")
            written.append(rel)
        mark_skills_dirty()
    # Record the rendered bundle as a version snapshot of the current SKILL.md.
    return {
        "name": cleaned,
        "status": status,
        "filename": result["filename"],
        "files": written,
        "rendered": render_skill_md(cleaned, description, body),
    }
