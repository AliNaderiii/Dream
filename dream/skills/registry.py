"""Cached, bounded skill registry over the workspace ``skills/`` tree.

Scans two shapes in the existing location:

* ``skills/*.txt`` — v1 hand-editable procedures (preserved).
* ``skills/<name>/SKILL.md`` — v2 agentskills.io documents.

The scan is bounded (file count + depth + size) and cached.  A turn does
not rescan unless a writer marks the registry dirty or the directory
signature (paths + mtimes + sizes) changed, so a hand edit still lands
on the next use without a rebuild step.

Invalid files fail per-skill: they become :class:`SkillProblem` rows with
bilingual detail and never prevent other skills from loading.  Name
collisions and unsafe names are reported the same way.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from dream import tools
from dream.memory import normalize_fa
from dream.skills.format import (
    DESCRIPTION_MAX_CHARS,
    SkillFormatError,
    parse_skill_md,
    slash_from_legacy_name,
)

# Re-export so a test can pin identity with dream.memory.normalize_fa.
normalize_fa = normalize_fa

MAX_SKILL_FILES = 200
MAX_SKILL_FILE_BYTES = 65_536
SKILL_CATALOG_BUDGET_CHARS = 8_000
SKILLS_DIR_NAME = "skills"
LEGACY_SUFFIX = ".txt"
SKILL_MD_NAME = "SKILL.md"

# Slash names that belong to the CLI / phone surface, never to a skill.
RESERVED_SLASH_NAMES = frozenset(
    {
        "mem",
        "mems",
        "stats",
        "forget",
        "dedupe",
        "pin",
        "remind",
        "reminder",
        "reminders",
        "reminds",
        "unremind",
        "skill",
        "skills",
        "tools",
        "plan",
        "usage",
        "route",
        "reset",
        "help",
        "exit",
        "learn",
    }
)

# Gloss: «نام مهارت تکراری است؛ یکی را عوض کن. فایل دیگر: {other}»
_ERR_COLLISION_FA = (
    "\u0646\u0627\u0645 \u0645\u0647\u0627\u0631\u062a \u062a\u06a9\u0631\u0627\u0631\u06cc "
    "\u0627\u0633\u062a\u061b \u06cc\u06a9\u06cc \u0631\u0627 \u0639\u0648\u0636 \u06a9\u0646. "
    "\u0641\u0627\u06cc\u0644 \u062f\u06cc\u06af\u0631: {other}"
)
_ERR_COLLISION_EN = " Duplicate skill name; rename one. Other file: {other}."

# Gloss: «نام مهارت برای دستور اسلش رزرو شده است.»
_ERR_RESERVED_FA = (
    "\u0646\u0627\u0645 \u0645\u0647\u0627\u0631\u062a \u0628\u0631\u0627\u06cc "
    "\u062f\u0633\u062a\u0648\u0631 \u0627\u0633\u0644\u0634 \u0631\u0632\u0631\u0648 "
    "\u0634\u062f\u0647 \u0627\u0633\u062a."
)
_ERR_RESERVED_EN = " Skill name is reserved as a slash command."

# Gloss: «سقف پویش مهارت‌ها پر شد؛ این فایل خوانده نشد.»
_ERR_BOUND_FA = (
    "\u0633\u0642\u0641 \u067e\u0648\u06cc\u0634 \u0645\u0647\u0627\u0631\u062a\u200c\u0647\u0627 "
    "\u067e\u0631 \u0634\u062f\u061b \u0627\u06cc\u0646 \u0641\u0627\u06cc\u0644 \u062e\u0648"
    "\u0627\u0646\u062f\u0647 "
    "\u0646\u0634\u062f."
)
_ERR_BOUND_EN = " Skill scan bound reached; this file was not loaded."

# Gloss: «مهارت‌های نصب‌شده (فقط نام و توضیح؛ برای متن کامل skill_view را صدا بزن):»
_CATALOG_HEADER = (
    "\n\n"
    "\u0645\u0647\u0627\u0631\u062a\u200c\u0647\u0627\u06cc \u0646\u0635\u0628\u200c\u0634\u062f"
    "\u0647 "
    "(\u0641\u0642\u0637 \u0646\u0627\u0645 \u0648 \u062a\u0648\u0636\u06cc\u062d\u061b \u0628"
    "\u0631\u0627\u06cc "
    "\u0645\u062a\u0646 \u06a9\u0627\u0645\u0644 skill_view \u0631\u0627 \u0635\u062f\u0627 "
    "\u0628\u0632\u0646):"
)


def _skills_dir() -> Path:
    return tools.WORKSPACE_ROOT / SKILLS_DIR_NAME


def _rel(path: Path) -> str:
    return f"{SKILLS_DIR_NAME}/{path.relative_to(_skills_dir()).as_posix()}"


def _signature(directory: Path) -> tuple[Any, ...]:
    """Paths + mtime + size; a hand edit changes this and busts the cache."""
    if not directory.is_dir():
        return ()
    entries: list[tuple[str, int, int]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = [
                name
                for name in sorted(dirnames)
                if not name.startswith(".") and name != "__pycache__"
            ]
            depth = Path(dirpath).relative_to(directory).parts
            if len(depth) > 2:
                dirnames.clear()
                continue
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                path = Path(dirpath) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append((str(path), int(stat.st_mtime_ns), int(stat.st_size)))
                if len(entries) >= MAX_SKILL_FILES + 8:
                    return tuple(entries)
    except OSError:
        return ()
    return tuple(entries)


class SkillRegistry:
    """One cached snapshot of the skills directory."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dirty = True
        self._signature: tuple[Any, ...] = ()
        self._skills: list[Any] = []
        self._problems: list[Any] = []

    def mark_dirty(self) -> None:
        with self._lock:
            self._dirty = True

    def load(self) -> tuple[list[Any], list[Any]]:
        from dream.skills import Skill, SkillProblem, parse_skill_text

        directory = _skills_dir()
        signature = _signature(directory)
        with self._lock:
            if not self._dirty and signature == self._signature:
                return list(self._skills), list(self._problems)
            skills, problems = self._scan(directory, Skill, SkillProblem, parse_skill_text)
            self._skills = skills
            self._problems = problems
            self._signature = signature
            self._dirty = False
            return list(skills), list(problems)

    def _scan(
        self, directory: Path, Skill: Any, SkillProblem: Any, parse_skill_text: Any
    ) -> tuple[list[Any], list[Any]]:
        skills: list[Any] = []
        problems: list[Any] = []
        if not directory.is_dir():
            return skills, problems

        seen_norm: dict[str, str] = {}
        seen_slash: dict[str, str] = {}
        scanned = 0

        def _take() -> bool:
            nonlocal scanned
            scanned += 1
            return scanned <= MAX_SKILL_FILES

        # v1 files first (stable sorted), then v2 directories.
        for path in sorted(directory.glob(f"*{LEGACY_SUFFIX}")):
            if not path.is_file():
                continue
            relative = _rel(path)
            if not _take():
                problems.append(SkillProblem(relative, _ERR_BOUND_FA + _ERR_BOUND_EN))
                continue
            skill_or_problem = _load_legacy(path, relative, Skill, SkillProblem, parse_skill_text)
            if isinstance(skill_or_problem, SkillProblem):
                problems.append(skill_or_problem)
                continue
            collision = _register_names(skill_or_problem, seen_norm, seen_slash)
            if collision is not None:
                problems.append(SkillProblem(relative, collision))
                continue
            skills.append(skill_or_problem)

        for child in sorted(directory.iterdir(), key=lambda p: p.name):
            if not child.is_dir() or child.name.startswith("."):
                continue
            md = child / SKILL_MD_NAME
            relative = (
                _rel(md)
                if md.exists()
                else f"{SKILLS_DIR_NAME}/{child.name}/{SKILL_MD_NAME}"
            )
            if not md.is_file():
                continue
            if not _take():
                problems.append(SkillProblem(relative, _ERR_BOUND_FA + _ERR_BOUND_EN))
                continue
            skill_or_problem = _load_v2(md, child.name, relative, Skill, SkillProblem)
            if isinstance(skill_or_problem, SkillProblem):
                problems.append(skill_or_problem)
                continue
            collision = _register_names(skill_or_problem, seen_norm, seen_slash)
            if collision is not None:
                problems.append(SkillProblem(relative, collision))
                continue
            skills.append(skill_or_problem)

        return skills, problems


def _register_names(
    skill: Any, seen_norm: dict[str, str], seen_slash: dict[str, str]
) -> str | None:
    key = normalize_fa(skill.name).strip()
    slash_key = normalize_fa(skill.slash).strip()
    if key in seen_norm:
        return _ERR_COLLISION_FA.format(other=seen_norm[key]) + _ERR_COLLISION_EN.format(
            other=seen_norm[key]
        )
    if slash_key and slash_key in seen_slash and seen_slash[slash_key] != skill.filename:
        return _ERR_COLLISION_FA.format(other=seen_slash[slash_key]) + _ERR_COLLISION_EN.format(
            other=seen_slash[slash_key]
        )
    reserved = slash_key.lower() if slash_key.isascii() else slash_key
    if reserved in RESERVED_SLASH_NAMES:
        return _ERR_RESERVED_FA + _ERR_RESERVED_EN
    seen_norm[key] = skill.filename
    if slash_key:
        seen_slash[slash_key] = skill.filename
    return None


def _load_legacy(
    path: Path, relative: str, Skill: Any, SkillProblem: Any, parse_skill_text: Any
) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return SkillProblem(relative, f"unreadable: {exc}")
    if len(raw) > MAX_SKILL_FILE_BYTES:
        return SkillProblem(relative, "file is too large to be a skill")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return SkillProblem(relative, "file is not valid UTF-8")
    try:
        name, description, steps = parse_skill_text(text)
    except ValueError as exc:
        return SkillProblem(relative, str(exc))
    slash = slash_from_legacy_name(name) or slash_from_legacy_name(path.stem)
    return Skill(
        name,
        description,
        tuple(steps),
        relative,
        body=text,
        slash=slash,
        kind="legacy",
    )


def _load_v2(path: Path, folder: str, relative: str, Skill: Any, SkillProblem: Any) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return SkillProblem(relative, f"unreadable: {exc}")
    if len(raw) > MAX_SKILL_FILE_BYTES:
        return SkillProblem(relative, "file is too large to be a skill")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return SkillProblem(relative, "file is not valid UTF-8")
    try:
        document = parse_skill_md(text, folder=folder)
    except SkillFormatError as exc:
        return SkillProblem(relative, str(exc))
    return Skill(
        document.name,
        document.description,
        document.steps,
        relative,
        body=document.body,
        slash=document.name,
        kind="skill_md",
    )


_REGISTRY = SkillRegistry()


def get_registry() -> SkillRegistry:
    return _REGISTRY


def mark_skills_dirty() -> None:
    _REGISTRY.mark_dirty()


def load_skills_cached() -> tuple[list[Any], list[Any]]:
    return _REGISTRY.load()


def find_by_name(query: str) -> Any | None:
    """Exact name or slash-name match through the shared normalizer."""
    needle = normalize_fa(query).strip()
    if not needle:
        return None
    skills, _ = load_skills_cached()
    for skill in skills:
        if normalize_fa(skill.name).strip() == needle:
            return skill
        if skill.slash and normalize_fa(skill.slash).strip() == needle:
            return skill
    return None


def render_skill_catalog(
    budget_chars: int = SKILL_CATALOG_BUDGET_CHARS,
) -> tuple[str, list[Any]]:
    """Name + description only, never a body, under ``budget_chars``.

    Returns ``(block, injected_skills)``.  The block is empty when nothing
    fits or no skills are installed.  Bodies are structurally absent: the
    renderer never reads ``skill.body`` into the string.
    """
    if budget_chars <= 0:
        return "", []
    skills, _ = load_skills_cached()
    if not skills:
        return "", []
    header = _CATALOG_HEADER
    if len(header) >= budget_chars:
        return "", []
    lines: list[str] = []
    injected: list[Any] = []
    used = len(header)
    for skill in skills:
        slash = skill.slash or slash_from_legacy_name(skill.name)
        desc = skill.description
        if len(desc) > DESCRIPTION_MAX_CHARS:
            desc = desc[: DESCRIPTION_MAX_CHARS]
        line = f"\n/{slash} — {desc}"
        if used + len(line) > budget_chars:
            break
        # Deliberate: only slash + description. Body is not consulted.
        lines.append(line)
        injected.append(skill)
        used += len(line)
    if not lines:
        return "", []
    return header + "".join(lines), injected
