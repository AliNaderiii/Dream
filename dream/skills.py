"""File-backed skills: hand-editable procedures the assistant can find again.

A memory stores what is true; a skill stores how to do something. Skills are
not rows in the database — they are UTF-8 text files in ``skills/`` under the
workspace root, so the owner can open one in any editor, correct a wrong
step, and have the correction take effect on the very next use. Nothing is
cached: every load reads the directory again, so there is no rebuild step
and no stale state between sessions.

File format (readable on purpose):

    name: چای دم کردن
    description: وقتی کاربر می‌خواهد چای درست کند یا طرز تهیه چای را بپرسد
    steps:
    1. کتری را با آب تازه پر کن
    2. ...

Labels may also be written in Persian (``نام:``, ``توضیح:``, ``مراحل:``) —
the parser accepts both spellings so a hand-written file is never refused for
choosing the wrong one. Step lines may carry ``-``, ``*``, ``1.`` or ``۱)``
markers; the marker is not part of the step. All three fields are required: a
file without a name, a description, or at least one step is reported as
broken and skipped, never fatal. Files that are not valid UTF-8, or that
exceed a generous size cap, are reported and skipped the same way.

Matching reuses the existing linguistic pipeline — ``normalize_fa``, the
suffix stemmer and the synonym index from :mod:`dream.memory` — instead of
inventing a third mechanism. A skill's matching surface is its name plus
description (the declared "when it applies"), never its steps: step content
would false-positive any request that mentions an action. Scoring is
skill-side coverage, the same formula ``prompt_reminders`` uses: the
fraction of the skill's content stems that appear among the query's
synonym-expanded stems. Two guards keep a single generic shared word from
summoning a skill (the stemmer conflates «درست» and «درس», and every
description shares scaffolding words): a match needs at least a third of the
skill's stems covered, and either two shared stems or full coverage.

This module knows nothing about SQLite, and the store knows nothing about
skills; the only dependencies are the text helpers above and the workspace
boundary helper in :mod:`dream.tools`, referenced through the module at call
time so tests that relocate ``WORKSPACE_ROOT`` see every skill move with it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from dream import tools
from dream.memory import _SYNONYM_INDEX, Memory, _stem_fa, _tokenize, normalize_fa
from dream.providers import MemoryProvider
from dream.reminders import Reminder

__all__ = [
    "Skill",
    "SkillProblem",
    "SKILL_SAVE_WARNING",
    "find_skill",
    "guard_skill_save_claim",
    "load_skills",
    "parse_skill_text",
    "render_skill_text",
    "SKILLS_USAGE",
    "SkillPromptProvider",
    "save_skill",
    "score_skills",
    "unsaved_skill_claim",
    "validate_name",
]

SKILLS_DIR_NAME = "skills"
SKILL_SUFFIX = ".txt"

# A skill is one screenful of prose; anything past 64 KiB is not a procedure
# the owner wrote by hand — it is reported as a problem instead of being read.
MAX_SKILL_FILE_BYTES = 65_536

# Matching bar, chosen against the Persian test battery: one third of the
# skill's content stems must be covered (paraphrases drop words), and a lone
# shared stem is never enough unless it is the skill's entire surface.
MIN_COVERAGE = 1.0 / 3.0
MIN_SHARED_STEMS = 2

# Scaffolding words with no topic content: politeness and request frames,
# auxiliaries, function words, question words. Written as backslash-u escapes
# with a plain-Persian gloss, matching the synonym-table convention.
# Gloss: وقتی اگر کاربر است هست باشد شود می خواهد خواهم بخواهد کند کن کنم
#        کنیم کرد کردن کرده بگو بگم بگوید گفت یا و را از به با در که برای تا
#        این آن هر همه چطور چگونه چی چه چقدر پرسیدن پرسید بپرس
_STOPWORDS: tuple[str, ...] = (
    "\u0648\u0642\u062a\u06cc", "\u0627\u06af\u0631", "\u06a9\u0627\u0631\u0628\u0631",
    "\u0627\u0633\u062a", "\u0647\u0633\u062a", "\u0628\u0627\u0634\u062f", "\u0634\u0648\u062f",
    "\u0645\u06cc", "\u062e\u0648\u0627\u0647\u062f", "\u062e\u0648\u0627\u0647\u0645",
    "\u0628\u062e\u0648\u0627\u0647\u062f", "\u06a9\u0646\u062f", "\u06a9\u0646",
    "\u06a9\u0646\u0645", "\u06a9\u0646\u06cc\u0645", "\u06a9\u0631\u062f",
    "\u06a9\u0631\u062f\u0646", "\u06a9\u0631\u062f\u0647", "\u0628\u06af\u0648",
    "\u0628\u06af\u0645", "\u0628\u06af\u0648\u06cc\u062f", "\u06af\u0641\u062a",
    "\u06cc\u0627", "\u0648", "\u0631\u0627", "\u0627\u0632", "\u0628\u0647",
    "\u0628\u0627", "\u062f\u0631", "\u06a9\u0647", "\u0628\u0631\u0627\u06cc",
    "\u062a\u0627", "\u0627\u06cc\u0646", "\u0622\u0646", "\u0647\u0631", "\u0647\u0645\u0647",
    "\u0686\u0637\u0648\u0631", "\u0686\u06af\u0648\u0646\u0647", "\u0686\u06cc",
    "\u0686\u0647", "\u0686\u0642\u062f\u0631", "\u067e\u0631\u0633\u06cc\u062f\u0646",
    "\u067e\u0631\u0633\u06cc\u062f", "\u0628\u067e\u0631\u0633",
)

_STOP_STEMS: frozenset[str] = frozenset(
    _stem_fa(token) for word in _STOPWORDS for token in _tokenize(word)
)

# Both Latin and Persian label spellings parse; the writer emits Latin so the
# grammar stays unambiguous in editors that mangle RTL punctuation.
_LABELS = {
    "name": "name",
    "description": "description",
    "steps": "steps",
    "\u0646\u0627\u0645": "name",  # نام
    "\u062a\u0648\u0636\u06cc\u062d": "description",  # توضیح
    "\u0645\u0631\u062d\u0644\u0647": "steps",  # مرحله (treated as steps)
    "\u0645\u0631\u0627\u062d\u0644": "steps",  # مراحل
}
_LABEL_RE = re.compile(r"^([^\s:]{1,16})\s*:\s*(.*)$")
_STEP_MARKER_RE = re.compile(r"^(?:[-*•]|[0-9۰-۹]+[.)])\s+")

# Recognized step object keys: text keys carry the step instruction, index keys
# carry ignorable numbering metadata (e.g. {"number": 1, "step": "..."}).
_STEP_TEXT_KEYS: frozenset[str] = frozenset({
    "step",
    "text",
    "description",
    "content",
    "instruction",
    "detail",
    "\u0645\u0631\u062d\u0644\u0647",  # مرحله
    "\u0645\u062a\u0646",     # متن
    "\u062a\u0648\u0636\u06cc\u062d",  # توضیح
})

_STEP_INDEX_KEYS: frozenset[str] = frozenset({
    "number",
    "index",
    "step_number",
    "order",
    "num",
    "id",
    "no",
    "\u0634\u0645\u0627\u0631\u0647",  # شماره
    "\u0631\u062f\u06cc\u0641",   # ردیف
})

# Characters that are path separators, drive markers, or illegal in Windows
# file names; the workspace may be copied to a Windows machine (run.bat).
_FORBIDDEN_NAME_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class Skill:
    """One parsed skill file: what it is called, when it applies, its steps."""

    name: str
    description: str
    steps: tuple[str, ...]
    filename: str


@dataclass(frozen=True, slots=True)
class SkillProblem:
    """One unusable skill file and why it was skipped. Never fatal."""

    filename: str
    detail: str


def _skills_dir() -> Any:
    """Return the skills directory under the current workspace root."""
    return tools.WORKSPACE_ROOT / SKILLS_DIR_NAME


def validate_name(name: str) -> str:
    """Return the cleaned skill name or raise ``ValueError`` with the reason.

    A name becomes one flat file inside ``skills/``; anything shaped like a
    path — a separator, a parent reference, an absolute or drive-qualified
    form — is refused before the file system is ever consulted.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("skill name is empty")
    if _FORBIDDEN_NAME_CHARS.search(cleaned):
        raise ValueError(f"skill name contains a forbidden character: {name!r}")
    if ".." in cleaned:
        raise ValueError(f"skill name contains a parent directory reference: {name!r}")
    return cleaned


def parse_skill_text(text: str) -> tuple[str, str, list[str]]:
    """Parse skill file text into ``(name, description, steps)``.

    Forgiving by design, because the owner edits these files by hand: blank
    lines are ignored, both label spellings are accepted, and step markers
    are stripped. Raises ``ValueError`` naming the first missing part.
    """
    name: str | None = None
    description: str | None = None
    steps: list[str] = []
    section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _LABEL_RE.match(line)
        if match:
            field = _LABELS.get(normalize_fa(match.group(1)).lower())
            if field == "name":
                name = match.group(2).strip()
                section = field
                continue
            if field == "description":
                description = match.group(2).strip()
                section = field
                continue
            if field == "steps":
                section = field
                continue
        if section == "steps":
            steps.append(_STEP_MARKER_RE.sub("", line).strip())
    if not name:
        raise ValueError("skill file has no name line")
    if not description:
        raise ValueError("skill file has no description line")
    steps = [step for step in steps if step]
    if not steps:
        raise ValueError("skill file has no steps")
    return name, description, steps


def render_skill_text(name: str, description: str, steps: list[str]) -> str:
    """Render the canonical skill file text that ``save_skill`` writes."""
    lines = [f"name: {name}", f"description: {description}", "steps:"]
    lines.extend(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    return "\n".join(lines) + "\n"


def _coerce_step(step: Any) -> str:
    """Coerce one step item into clean text or raise ``ValueError``.

    Data Integrity rule: If a shape cannot be read confidently, refuse the
    write with a descriptive message rather than storing a repr or guessing.
    """
    if isinstance(step, bool):
        raise ValueError("unusable step shape: boolean is not a step")
    if isinstance(step, (int, float)):
        return str(step).strip()
    if isinstance(step, str):
        cleaned = step.strip()
        if not cleaned:
            raise ValueError("step text is empty")
        return cleaned
    if isinstance(step, dict):
        if not step:
            raise ValueError("unusable step shape: empty dictionary")
        for val in step.values():
            if isinstance(val, (dict, list)):
                raise ValueError(f"unusable step shape: nested structure in {step!r}")

        text_candidates: dict[str, str] = {}
        index_candidates: dict[str, Any] = {}
        other_candidates: dict[str, Any] = {}

        for k, val in step.items():
            key_norm = normalize_fa(str(k)).lower().strip()
            if key_norm in _STEP_INDEX_KEYS:
                index_candidates[key_norm] = val
            elif key_norm in _STEP_TEXT_KEYS:
                if isinstance(val, bool):
                    raise ValueError(f"unusable step shape: boolean value in {step!r}")
                if isinstance(val, (str, int, float)):
                    t = str(val).strip()
                    if t:
                        text_candidates[key_norm] = t
            else:
                other_candidates[key_norm] = val

        if text_candidates:
            unique = set(text_candidates.values())
            if len(unique) > 1:
                raise ValueError(
                    f"unusable step shape: ambiguous conflicting text keys in {step!r}"
                )
            return next(iter(unique))

        if len(step) == 1:
            k, val = next(iter(step.items()))
            if isinstance(val, bool):
                raise ValueError(f"unusable step shape: boolean value in {step!r}")
            key_norm = normalize_fa(str(k)).lower().strip()
            if key_norm in _STEP_INDEX_KEYS:
                raise ValueError(f"unusable step shape: index-only dictionary in {step!r}")
            if isinstance(val, (str, int, float)):
                t = str(val).strip()
                if t:
                    return t
                raise ValueError(f"unusable step shape: empty text in {step!r}")

        if index_candidates and len(other_candidates) == 1:
            k, val = next(iter(other_candidates.items()))
            if isinstance(val, bool):
                raise ValueError(f"unusable step shape: boolean value in {step!r}")
            if isinstance(val, (str, int, float)):
                t = str(val).strip()
                if t:
                    return t

        if index_candidates and not other_candidates and not text_candidates:
            raise ValueError(f"unusable step shape: index-only dictionary in {step!r}")

        raise ValueError(f"unusable step shape: cannot confidently read step from {step!r}")

    raise ValueError(f"unusable step shape: {type(step).__name__} is not a valid step")


def save_skill(name: str, description: str, steps: Any) -> str:
    """Write one skill file through the workspace boundary helper.

    Returns the workspace-relative filename. Overwriting an existing name is
    how a skill is corrected. Raises ``ValueError`` on a refused name or on
    missing content; the tool boundary turns that into a structured error.
    """
    cleaned = validate_name(name)
    description = description.strip()
    if not description:
        raise ValueError("skill description is empty")
    if isinstance(steps, str):
        steps = steps.splitlines()
    if not isinstance(steps, (list, tuple)):
        raise ValueError(f"skill steps must be a list, got {type(steps).__name__}")
    cleaned_steps = [_coerce_step(step) for step in steps]
    cleaned_steps = [step for step in cleaned_steps if step]
    if not cleaned_steps:
        raise ValueError("skill has no steps")
    directory = _skills_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = tools._safe_path(f"{SKILLS_DIR_NAME}/{cleaned}{SKILL_SUFFIX}")
    path.write_text(
        render_skill_text(cleaned, description, cleaned_steps), encoding="utf-8"
    )
    return f"{SKILLS_DIR_NAME}/{cleaned}{SKILL_SUFFIX}"


def load_skills() -> tuple[list[Skill], list[SkillProblem]]:
    """Read every skill file fresh from the workspace; never raise.

    Each ``.txt`` file is parsed on its own: one malformed, unreadable, or
    oversized file becomes a :class:`SkillProblem` and every other skill
    still loads. Files without the skill suffix are not skills at all and
    are ignored rather than reported.
    """
    skills: list[Skill] = []
    problems: list[SkillProblem] = []
    directory = _skills_dir()
    if not directory.is_dir():
        return skills, problems
    for path in sorted(directory.glob(f"*{SKILL_SUFFIX}")):
        relative = f"{SKILLS_DIR_NAME}/{path.name}"
        try:
            raw = path.read_bytes()
        except OSError as exc:
            problems.append(SkillProblem(relative, f"unreadable: {exc}"))
            continue
        if len(raw) > MAX_SKILL_FILE_BYTES:
            problems.append(SkillProblem(relative, "file is too large to be a skill"))
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(SkillProblem(relative, "file is not valid UTF-8"))
            continue
        try:
            name, description, steps = parse_skill_text(text)
        except ValueError as exc:
            problems.append(SkillProblem(relative, str(exc)))
            continue
        skills.append(Skill(name, description, tuple(steps), relative))
    return skills, problems


def _content_stems(text: str) -> set[str]:
    """Stem ``text`` and drop scaffolding words, leaving topic stems only."""
    return {
        stem
        for stem in (_stem_fa(token) for token in _tokenize(text))
        if stem not in _STOP_STEMS
    }


def _expanded_query_stems(query: str) -> set[str]:
    """Content stems of the query plus every synonym-group expansion."""
    stems = _content_stems(query)
    expanded = set(stems)
    for stem in stems:
        expanded.update(_SYNONYM_INDEX.get(stem, ()))
    return expanded


def _skill_stems(skill: Skill) -> frozenset[str]:
    """The skill's matching surface: name and description, never the steps."""
    return frozenset(_content_stems(f"{skill.name} {skill.description}"))


# The suffix stemmer is deliberately shallow, so two inflections of one word
# can land on stems where one merely prefixes the other (measured during the
# adversarial pass: «دوست» vs «دوستش» gives دوست/دوست — the bare form sheds
# its ت — and «بنویسم» vs «بنویسد» gives بنویس/بنویسد — د is not in the
# suffix table). Exact-set matching would miss all of those, so two stems
# count as equal when one prefixes the other, with a floor of three letters:
# two-letter «دم» (brewing) must never claim «دما» (the weather report).
_MIN_PREFIX_STEM = 3


def _stem_match(left: str, right: str) -> bool:
    """Equality of stems, allowing one measured inflection asymmetry."""
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= _MIN_PREFIX_STEM and longer.startswith(shorter)


def _shared_count(stems: frozenset[str], query_stems: set[str]) -> int:
    """How many of the skill's stems are covered by the expanded query."""
    return sum(
        1 for stem in stems if any(_stem_match(stem, qstem) for qstem in query_stems)
    )


def score_skills(query: str, *, permissive: bool = False) -> list[Skill]:
    """Rank skills clearing the matching bar, best first; ties by name.

    Score = fraction of the skill's own content stems covered by the
    synonym-expanded query. A skill with an empty content surface cannot
    match anything.

    Two bars exist:

    - Strict (``permissive=False``): a skill needs at least a third of its
      stems covered and either two shared stems or full coverage, so one
      generic word never summons a procedure the assistant would then
      follow. Used by the ``use_skill`` tool (dispatch).

    - Permissive (``permissive=True``): a single shared content stem is
      enough. The owner typed the query and reads the result with his own
      eyes, so a false negative (concluding the skill was never saved) is
      worse than a low-ranked extra hit. Used by ``/skill QUERY`` (search).
    """
    query_stems = _expanded_query_stems(query)
    ranked: list[tuple[float, Skill]] = []
    skills, _ = load_skills()
    for skill in skills:
        stems = _skill_stems(skill)
        if not stems:
            continue
        shared = _shared_count(stems, query_stems)
        coverage = shared / len(stems) if stems else 0
        if permissive:
            if shared < 1:
                continue
        else:
            if coverage < MIN_COVERAGE:
                continue
            if shared < MIN_SHARED_STEMS and coverage < 1.0:
                continue
        ranked.append((coverage, skill))
    ranked.sort(key=lambda item: (-item[0], item[1].name))
    return [skill for _, skill in ranked]


def find_skill(query: str, *, permissive: bool = False) -> Skill | None:
    """Return the best skill for a Persian request, or ``None`` for no match.

    ``permissive`` selects the search bar (``/skill``) vs the dispatch bar
    (``use_skill``). Dispatch stays strict.
    """
    ranked = score_skills(query, permissive=permissive)
    return ranked[0] if ranked else None


# ---------------------------------------------------------------------------
# Save-claim guard: a reply that claims a skill was saved must be backed by a
# completed save in the same turn.
#
# The M11 rule against claiming a save without calling save_skill existed only
# as a sentence in the system prompt. The owner was once told a step was added
# and heard all three steps recited while the file on disk still held one
# step; a prompt sentence is a request, so this milestone turns it into a
# property of every finished turn.
#
# Basis chosen: outcome, not attempt. A turn either changed a skill file or it
# did not, so the guard asks whether a save_skill call *completed* (was
# allowed and returned ``status: ok``) rather than whether a call was merely
# recorded. A blocked call and a call whose write failed are both "no save".
#
# The reply must claim a *skill* save, not any save: a save word alone raised
# two false positives on note and fact replies (those tools legitimately say
# something was saved), so a skill noun is required inside the claim window.
# Offers and questions are excluded by construction: only completed past and
# perfective verb forms are claim verbs, and a question word before the claim
# vetoes it.
#
# Negation is handled by design, not by word order. The Persian negative
# prefix attaches to the front of the verb (ذخیره شد vs ذخیره نشد), so the
# detector matches whole normalized tokens against a closed set of positive
# past forms; the negative forms (نشد، نشده، نکردم، نیست، ...) are never
# members of that set, and a test asserts the two sets are disjoint.
#
# The four holes found in the M13 candidate detector:
#   1  a blocked call still counting as a call -> closed: ``allowed`` must be
#      True and the result must carry ``status: ok``.
#   2  the wrong skill counting                -> closed: when the claim names
#      a procedure and a save completed, the saved skill's name must share a
#      content stem with the claimed name; a fully disjoint name (a tea
#      recipe satisfying a claim about the insurance procedure) is flagged.
#      A generic claim that names no procedure cannot be disproved and is
#      left alone — stated as the boundary.
#   3  paraphrase evading the save word       -> closed: the receive/put/write
#      families (دریافت، گرفت، گذاشت، نوشت) are claim verbs too when they
#      land on a file («در فایل»); «از فایل» marks a read and vetoes.
#   4  negation surviving by word-order luck  -> closed by design, see above.
# ---------------------------------------------------------------------------

# Gloss: روش مهارت مهارتها قدم قدمها مرحله مراحل دستورالعمل دستورالعملها رویه
#        روال راهنما گام — skill nouns that make a save word a *skill* claim.
_SKILL_NOUNS: frozenset[str] = frozenset({
    "\u0631\u0648\u0634",                      # روش
    "\u0645\u0647\u0627\u0631\u062a",          # مهارت
    "\u0642\u062f\u0645",                      # قدم
    "\u0645\u0631\u062d\u0644\u0647",          # مرحله
    "\u0645\u0631\u0627\u062d\u0644",          # مراحل
    "\u062f\u0633\u062a\u0648\u0631\u0627\u0644\u0639\u0645\u0644",  # دستورالعمل
    "\u0631\u0648\u06cc\u0647",                # رویه
    "\u0631\u0648\u0627\u0644",                # روال
    "\u0631\u0627\u0647\u0646\u0645\u0627",    # راهنما
    "\u06af\u0627\u0645",                      # گام
})

# Gloss: ذخیره ثبت اضافه قرار دریافت نوشته — nominal save stems that form a
# claim when followed by a completed past verb (ذخیره شد، ثبت کرده، ...).
_SAVE_STEMS: frozenset[str] = frozenset({
    "\u0630\u062e\u06cc\u0631\u0647",          # ذخیره
    "\u062b\u0628\u062a",                      # ثبت
    "\u0627\u0636\u0627\u0641\u0647",          # اضافه
    "\u0642\u0631\u0627\u0631",                # قرار
    "\u062f\u0631\u06cc\u0627\u0641\u062a",    # دریافت
    "\u0646\u0648\u0634\u062a\u0647",          # نوشته
})

# Gloss: نوشتم نوشت گرفتم گرفت گذاشتم گذاشت گذاشته — standalone past verbs
# that claim a write; these only count as claims when «فایل» is in the window.
_STANDALONE_SAVE_VERBS: frozenset[str] = frozenset({
    "\u0646\u0648\u0634\u062a\u0645",          # نوشتم
    "\u0646\u0648\u0634\u062a",                # نوشت
    "\u06af\u0631\u0641\u062a\u0645",          # گرفتم
    "\u06af\u0631\u0641\u062a",                # گرفت
    "\u06af\u0630\u0627\u0634\u062a\u0645",    # گذاشتم
    "\u06af\u0630\u0627\u0634\u062a",          # گذاشت
    "\u06af\u0630\u0627\u0634\u062a\u0647",    # گذاشته
})

# Completed past and perfective verb forms, token-exact after normalization.
# The negative forms (نشد، نشده، نکردم، نیست، ...) are deliberately absent:
# they belong to _NEGATIVE_VERBS below and a test pins the two sets apart.
_PAST_VERBS: frozenset[str] = frozenset({
    "\u0634\u062f",                            # شد
    "\u0634\u062f\u0646\u062f",                # شدند
    "\u0634\u062f\u0647",                      # شده
    "\u0634\u062f\u0647\u0627\u0633\u062a",    # شدهاست
    "\u0634\u062f\u0647\u0627\u0646\u062f",    # شدهاند
    "\u06a9\u0631\u062f",                      # کرد
    "\u06a9\u0631\u062f\u0645",                # کردم
    "\u06a9\u0631\u062f\u06cc",                # کردی
    "\u06a9\u0631\u062f\u06cc\u0645",          # کردیم
    "\u06a9\u0631\u062f\u06cc\u062f",          # کردید
    "\u06a9\u0631\u062f\u0647\u0627\u0645",    # کردهام
    "\u06a9\u0631\u062f\u0647\u0627\u06cc\u0645",  # کردهایم
    "\u06a9\u0631\u062f\u0647\u0627\u06cc\u062f",  # کردهاید
    "\u06a9\u0631\u062f\u0647",                # کرده
    "\u06a9\u0631\u062f\u0647\u0627\u0633\u062a",  # کردهاست
    "\u06a9\u0631\u062f\u0647\u0627\u0646\u062f",  # کردهاند
    "\u06af\u0631\u0641\u062a",                # گرفت
    "\u06af\u0631\u0641\u062a\u0645",          # گرفتم
    "\u06af\u0631\u0641\u062a\u06cc",          # گرفتی
    "\u06af\u0631\u0641\u062a\u06cc\u0645",    # گرفتیم
    "\u06af\u0631\u0641\u062a\u06cc\u062f",    # گرفتید
    "\u06af\u0631\u0641\u062a\u0647\u0627\u0645",  # گرفتهام
    "\u06af\u0631\u0641\u062a\u0647\u0627\u06cc\u0645",  # گرفتهایم
    "\u06af\u0631\u0641\u062a\u0647",          # گرفته
    "\u06af\u0631\u0641\u062a\u0647\u0627\u0633\u062a",  # گرفتهایست → گرفتهاست
    "\u06af\u0631\u0641\u062a\u0647\u0627\u0646\u062f",  # گرفتهاند
    "\u0646\u0648\u0634\u062a",                # نوشت
    "\u0646\u0648\u0634\u062a\u0645",          # نوشتم
    "\u0646\u0648\u0634\u062a\u06cc",          # نوشتی
    "\u0646\u0648\u0634\u062a\u06cc\u0645",    # نوشتیم
    "\u0646\u0648\u0634\u062a\u06cc\u062f",    # نوشتید
    "\u0646\u0648\u0634\u062a\u0647\u0627\u0645",  # نوشتهام
    "\u0646\u0648\u0634\u062a\u0647\u0627\u06cc\u0645",  # نوشتهایم
    "\u0646\u0648\u0634\u062a\u0647",          # نوشته
    "\u0646\u0648\u0634\u062a\u0647\u0627\u0633\u062a",  # نوشتهاست
    "\u0646\u0648\u0634\u062a\u0647\u0627\u0646\u062f",  # نوشتهاند
})

# Trailing copula that completes a perfective: «ذخیره شده است», «کرده ایم».
_COPULA: frozenset[str] = frozenset({
    "\u0627\u0633\u062a",                      # است
    "\u0627\u0646\u062f",                      # اند
    "\u0627\u0645",                            # ام
    "\u0627\u06cc",                            # ای
    "\u0627\u06cc\u0645",                      # ایم
    "\u0627\u06cc\u062f",                      # اید
})

# The negative forms whose positive twins are in _PAST_VERBS. The Persian
# negative prefix attaches to the verb, so every denial differs from its
# claim by these whole tokens; the detector never matches them, by design.
# A test asserts this set is disjoint from _PAST_VERBS.
_NEGATIVE_VERBS: frozenset[str] = frozenset({
    "\u0646\u0634\u062f",                      # نشد
    "\u0646\u0634\u062f\u0646\u062f",          # نشدند
    "\u0646\u0634\u062f\u0647",                # نشده
    "\u0646\u0634\u062f\u0647\u0627\u0633\u062a",  # نشدهاست
    "\u0646\u0634\u062f\u0647\u0627\u0646\u062f",  # نشدهاند
    "\u0646\u06a9\u0631\u062f",                # نکرد
    "\u0646\u06a9\u0631\u062f\u0645",          # نکردم
    "\u0646\u06a9\u0631\u062f\u06cc",          # نکردی
    "\u0646\u06a9\u0631\u062f\u06cc\u0645",    # نکردیم
    "\u0646\u06a9\u0631\u062f\u06cc\u062f",    # نکردید
    "\u0646\u06a9\u0631\u062f\u0647",          # نکرده
    "\u0646\u06a9\u0631\u062f\u0647\u0627\u0645",  # نکردهام
    "\u0646\u06a9\u0631\u062f\u0647\u0627\u06cc\u0645",  # نکردهایم
    "\u0646\u06a9\u0631\u062f\u0647\u0627\u0633\u062a",  # نکردهاست
    "\u0646\u06a9\u0631\u062f\u0647\u0627\u0646\u062f",  # نکردهاند
    "\u0646\u06af\u0631\u0641\u062a",          # نگرفت
    "\u0646\u06af\u0631\u0641\u062a\u0645",    # نگرفتم
    "\u0646\u06af\u0631\u0641\u062a\u0647",    # نگرفته
    "\u0646\u0646\u0648\u0634\u062a",          # ننوشت
    "\u0646\u0646\u0648\u0634\u062a\u0645",    # ننوشتم
    "\u0646\u0646\u0648\u0634\u062a\u0647",    # ننوشته
    "\u0646\u06cc\u0633\u062a",                # نیست
    "\u0646\u06cc\u0633\u062a\u0645",          # نیستم
    "\u0646\u06cc\u0633\u062a\u06cc",          # نیستی
    "\u0646\u06cc\u0633\u062a\u06cc\u0645",    # نیستیم
    "\u0646\u06cc\u0633\u062a\u06cc\u062f",    # نیستید
    "\u0646\u06cc\u0633\u062a\u0646\u062f",    # نیستند
    "\u0646\u06af\u0630\u0627\u0634\u062a\u0645",  # نگذاشتم
    "\u0646\u06af\u0630\u0627\u0634\u062a",    # نگذاشت
})

# «قرار» only claims when it took/placed something: «قرار گرفت»; «قرار شد»
# (it was decided) is a plan, not a save, and must never be a claim.
_SAVE_VERB_ALLOWLIST: dict[str, frozenset[str]] = {
    "\u0642\u0631\u0627\u0631": frozenset({
        "\u06af\u0631\u0641\u062a",
        "\u06af\u0631\u0641\u062a\u0645",
        "\u06af\u0631\u0641\u062a\u06cc\u0645",
        "\u06af\u0631\u0641\u062a\u0647",
        "\u06af\u0631\u0641\u062a\u0647\u0627\u0645",
        "\u06af\u0631\u0641\u062a\u0647\u0627\u06cc\u0645",
        "\u06af\u0631\u0641\u062a\u0647\u0627\u0633\u062a",
        "\u06af\u0631\u0641\u062a\u0647\u0627\u0646\u062f",
    }),
}

# Stems needing «فایل» in the window, and the direction rule: «در فایل» marks
# a claim, «از فایل» marks a read. «روش را از فایل دریافت کردم» is a read;
# «روش دریافت شد و در فایل است» is a claim.
_FILE_REQUIRED_STEMS: frozenset[str] = frozenset({
    "\u062f\u0631\u06cc\u0627\u0641\u062a",    # دریافت
    "\u0646\u0648\u0634\u062a\u0647",          # نوشته
})

# Gloss: یادداشت یادداشتم یادداشتها ایمیل حافظه حافظهام — a non-skill
# container right before the claim verb means the save landed somewhere other
# than a skill file («این روش را در یادداشت ذخیره کردم»); the claim is not a
# skill-file claim. «فایل» itself is deliberately absent: «در فایل ذخیره شد»
# is exactly the claim we want.
_NON_SKILL_CONTAINERS: frozenset[str] = frozenset({
    "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a",  # یادداشت
    "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a\u0645",  # یادداشتم
    "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a\u0647\u0627",  # یادداشتها
    "\u0627\u06cc\u0645\u06cc\u0644",          # ایمیل
    "\u062d\u0627\u0641\u0638\u0647",          # حافظه
    "\u062d\u0627\u0641\u0638\u0647\u0627\u0645",  # حافظهام
})

# Gloss: قبلا قبل قبلی پیش پیشتر سابق وقتی اگر — past-reference and
# conditional markers inside the claim window mean the sentence refers to an
# earlier save (or a hypothetical one), not to a completion of this turn.
_PAST_REFERENCE: frozenset[str] = frozenset({
    "\u0642\u0628\u0644\u0627",                # قبلا
    "\u0642\u0628\u0644",                      # قبل
    "\u0642\u0628\u0644\u06cc",                # قبلی
    "\u067e\u06cc\u0634",                      # پیش
    "\u067e\u06cc\u0634\u062a\u0631",          # پیشتر
    "\u0633\u0627\u0628\u0642",                # سابق
    "\u0648\u0642\u062a\u06cc",                # وقتی
    "\u0627\u06af\u0631",                      # اگر
})

# Gloss: ایا مگر چرا کجا — question words before the claim mark a question
# about saving («آیا روش ذخیره شد؟»), never a claim.
_QUESTION_WORDS: frozenset[str] = frozenset({
    "\u0627\u06cc\u0627",                      # آیا → ایا
    "\u0645\u06af\u0631",                      # مگر
    "\u0686\u0631\u0627",                      # چرا
    "\u06a9\u062c\u0627",                      # کجا
})

# Gloss: بود بوده — a past-perfect marker right after the verb complex makes
# the sentence a reference to an earlier state («ذخیره شده بود»), not a
# completion of this turn.
_PAST_PERFECT_MARKERS: frozenset[str] = frozenset({
    "\u0628\u0648\u062f",                      # بود
    "\u0628\u0648\u062f\u0647",                # بوده
})

# Ordinal and temporal words dropped from a claimed-name span: «قدم دوم اضافه
# شد» names no procedure, so no wrong-skill comparison may use «دوم».
_NAME_DROP: frozenset[str] = frozenset({
    "\u0627\u0648\u0644",                      # اول
    "\u062f\u0648\u0645",                      # دوم
    "\u0633\u0648\u0645",                      # سوم
    "\u0686\u0647\u0627\u0631\u0645",          # چهارم
    "\u067e\u0646\u062c\u0645",                # پنجم
    "\u0634\u0634\u0645",                      # ششم
    "\u0647\u0641\u062a\u0645",                # هفتم
    "\u0647\u0634\u062a\u0645",                # هشتم
    "\u0646\u0647\u0645",                      # نهم
    "\u062f\u0647\u0645",                      # دهم
    "\u0622\u062e\u0631",                      # آخر
    "\u0622\u062e\u0631\u06cc",                # آخری
    "\u0641\u0627\u06cc\u0644",                # فایل
    "\u062a\u0627\u0632\u0647",                # تازه
    "\u0627\u0644\u0627\u0646",                # الان
    "\u062d\u0627\u0644\u0627",                # حالا
    "\u0627\u0645\u0631\u0648\u0632",          # امروز
    "\u062f\u0648\u0628\u0627\u0631\u0647",    # دوباره
    "\u0647\u0645\u06cc\u0646",                # همین
})

_CLAIM_WINDOW = 10          # tokens back from the verb to hunt the skill noun
_FULL_WINDOW = 8            # tokens each side of the verb for the فایل rule
_CONTAINER_LOOKBACK = 3     # tokens before the verb for a non-skill container


def _is_skill_noun(token: str) -> bool:
    """Whether a normalized token names a skill, honouring common morphology."""
    if token in _SKILL_NOUNS:
        return True
    if token[:-1] in _SKILL_NOUNS:  # indefinite -ی: روشی، مهارتی
        return True
    if _stem_fa(token) in _SKILL_NOUNS:  # attached plural: روشها، مهارتها
        return True
    return _stem_fa(token[:-1]) in _SKILL_NOUNS  # مهارتم، روشش


def _complex_span(tokens: list[str], index: int) -> tuple[int, int]:
    """End index of the (save stem, past verb, optional copula) at ``index``.

    ``index`` is the save stem or a standalone claim verb. Returns the index
    just past the completed verb complex so a following «بود» (past perfect,
    a reference, not a claim) can be recognised.
    """
    if index + 1 < len(tokens) and tokens[index + 1] in _PAST_VERBS:
        end = index + 2
        if end < len(tokens) and tokens[end] in _COPULA:
            return end + 1
        return end
    return index + 1


def _claim_context(tokens: list[str], index: int, end: int) -> dict[str, Any]:
    """The skill noun, claimed name span, and veto markers around a complex."""
    window = tokens[max(0, index - _CLAIM_WINDOW):index]
    noun_at = next(
        (j for j in range(len(window) - 1, -1, -1) if _is_skill_noun(window[j])),
        None,
    )
    claimed = (
        tokens[max(0, index - _CLAIM_WINDOW) + noun_at + 1 : index]
        if noun_at is not None
        else []
    )
    nearby = tokens[
        max(0, index - _FULL_WINDOW): min(len(tokens), end + _FULL_WINDOW)
    ]
    return {
        "noun_found": noun_at is not None,
        "claimed": claimed,
        "nearby": nearby,
        "before": tokens[max(0, index - _CLAIM_WINDOW):index],
        "after_end": tokens[end : min(len(tokens), end + 2)],
    }


def _vetoed_context(context: dict[str, Any], index: int, tokens: list[str]) -> bool:
    """Whether the context around a complex marks it as no claim.

    Question words, past-reference markers, a relative-clause «که», a
    non-skill container, a past-perfect «بود», or «از فایل» (a read) all
    make the sentence something other than a this-turn skill-save claim.
    """
    if any(word in context["before"] for word in _QUESTION_WORDS):
        return True
    if any(word in context["before"] for word in _PAST_REFERENCE):
        return True
    if index > 0 and tokens[index - 1] == "\u06a9\u0647":  # که — relative clause
        return True
    if any(word in context["before"][-_CONTAINER_LOOKBACK:] for word in _NON_SKILL_CONTAINERS):
        return True
    if any(word in context["after_end"] for word in _PAST_PERFECT_MARKERS):
        return True
    # «از فایل» marks a read («از فایل دریافت کردم»); the file rule below
    # still needs the file present to call something a claim.
    for j, token in enumerate(context["nearby"]):
        if token != "\u0641\u0627\u06cc\u0644":  # فایل
            continue
        if j > 0 and context["nearby"][j - 1] == "\u0627\u0632":  # از
            return True
    return False


def _claims_skill_save(reply: str) -> tuple[bool, list[str]]:
    """Detect a completed skill-save claim in a reply.

    Returns ``(found, claimed_names)`` where ``claimed_names`` are the
    procedure names the reply says were saved (empty when the claim names no
    procedure, e.g. «قدم اضافه شد»). Token membership in the positive past
    verb set is what makes negation a design property, not a word-order
    accident.
    """
    tokens = _tokenize(reply)
    claimed_names: list[str] = []
    found = False
    for index, token in enumerate(tokens):
        verb = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in _SAVE_STEMS:
            if verb not in _PAST_VERBS:
                continue
            allowlist = _SAVE_VERB_ALLOWLIST.get(token)
            if allowlist is not None and verb not in allowlist:
                continue
        elif token in _STANDALONE_SAVE_VERBS:
            pass
        else:
            continue
        end = _complex_span(tokens, index)
        context = _claim_context(tokens, index, end)
        if not context["noun_found"] or _vetoed_context(context, index, tokens):
            continue
        needs_file = (
            token in _FILE_REQUIRED_STEMS or token in _STANDALONE_SAVE_VERBS
        )
        if needs_file and "\u0641\u0627\u06cc\u0644" not in context["nearby"]:
            continue  # «گرفتم/نوشتم» without a file is not a skill-file claim
        found = True
        if context["claimed"]:
            claimed_names.append(_clean_claimed_name(context["claimed"]))
    return found, [name for name in claimed_names if name]


def _clean_claimed_name(tokens: list[str]) -> str:
    """Join claim-span tokens into a procedure name, dropping non-content.

    Stopwords, ordinals, digits, save stems, and past verbs carry no
    procedure content; a span reduced to those (e.g. «قدم دوم اضافه شد»)
    names no procedure.
    """
    kept: list[str] = []
    for token in tokens:
        if token in _STOPWORDS or token in _NAME_DROP:
            continue
        if token.isdigit():
            continue
        if token in _SAVE_STEMS or token in _PAST_VERBS or token in _STANDALONE_SAVE_VERBS:
            continue
        kept.append(token)
    return " ".join(kept)


def _successful_skill_saves(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calls that actually changed a skill file: allowed and reported ok.

    A blocked call (approval refused) and a call whose write failed both
    leave the disk untouched; only an allowed call whose result carries
    ``status: ok`` counts as a save.
    """
    completed: list[dict[str, Any]] = []
    for call in tool_calls:
        if str(call.get("name", "")) != "save_skill":
            continue
        if call.get("allowed") is not True:
            continue
        try:
            payload = json.loads(str(call.get("result", "")))
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("status") == "ok":
            completed.append(call)
    return completed


def _same_skill(claimed_name: str, saved_name: str) -> bool:
    """Whether a claimed procedure name and a saved skill name share content.

    Both sides run through the same content-stem pipeline, so «تمدید بیمه
    ماشین» matches a file saved under that name, and a tea recipe shares no
    stem with the insurance procedure.
    """
    claimed = _content_stems(claimed_name)
    saved = _content_stems(saved_name)
    return bool(claimed and saved and (claimed & saved))


def unsaved_skill_claim(reply: str, tool_calls: list[dict[str, Any]]) -> bool:
    """Whether a reply claims a skill save that no completed save backs.

    The basis is the outcome: a turn either changed a skill file or it did
    not. A claim with no completed ``save_skill`` call is unconfirmed; a
    claim that names a procedure is unconfirmed when every completed save
    wrote a fully different skill.
    """
    claimed, claimed_names = _claims_skill_save(reply)
    if not claimed:
        return False
    saves = _successful_skill_saves(tool_calls)
    if not saves:
        return True
    for name in claimed_names:
        saved_names = [str(save.get("arguments", {}).get("name", "")) for save in saves]
        if not any(_same_skill(name, saved) for saved in saved_names):
            return True
    return False


# Gloss: توجه: ادعای ذخیره‌شدن این روش تایید نشده است؛ فایل همان روش تغییر
# نکرده است.
SKILL_SAVE_WARNING = (
    "\n\n"
    "\u062a\u0648\u062c\u0647: "
    "\u0627\u062f\u0639\u0627\u06cc \u0630\u062e\u06cc\u0631\u0647\u200c\u0634\u062f\u0646 "
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 "
    "\u062a\u0627\u06cc\u06cc\u062f \u0646\u0634\u062f\u0647 \u0627\u0633\u062a\u061b "
    "\u0641\u0627\u06cc\u0644 \u0647\u0645\u0627\u0646 \u0631\u0648\u0634 "
    "\u062a\u063a\u06cc\u06cc\u0631 \u0646\u06a9\u0631\u062f\u0647 \u0627\u0633\u062a."
)


def guard_skill_save_claim(reply: str, tool_calls: list[dict[str, Any]]) -> str:
    """Return the reply, appending a Persian warning when its save claim is
    unconfirmed. A truthful reply — a claim backed by a completed save — is
    returned byte for byte.
    """
    if unsaved_skill_claim(reply, tool_calls):
        return reply + SKILL_SAVE_WARNING
    return reply

# The skills usage line, supplied to the system prompt through the M4
# ``contribute_prompt`` hook (wired in M10, sharpened in M11). Written as
# backslash-u escapes with a plain-Persian gloss, matching the prompt-string
# convention:
# «درباره مهارت‌ها: وقتی کاربر روش انجام کاری را قدم‌به‌قدم می‌گوید — مثلاً
# می‌گوید «یاد بگیر» یا «اول... بعد...» — این یک روش است، نه یک واقعیت درباره
# خودش؛ پس آن را در خاطره‌ها ذخیره نکن. همه قدم‌ها را جمع کن و با ابزار
# save_skill یک‌جا ذخیره کن؛ هر پیام را یک روش جدا نکن. اگر بعداً قدم
# تازه‌ای گفت، تمام قدم‌های قبلی و جدید را دوباره با همان نام با ابزار
# save_skill ذخیره کن. هرگز بدون فراخوانی ابزار save_skill ادعا نکن که روشی
# ذخیره یا اضافه شده است؛ تأیید ذخیره فقط پس از فراخوانی ابزار مجاز است.
# وقتی کاربر پرسید کاری را چطور انجام دهد، اول با ابزار use_skill بگرد؛ اگر
# روشی پیدا شد همان را دنبال کن و اگر نه، عادی پاسخ بده.»
SKILLS_USAGE = (
    "\n\n"
    "\u062f\u0631\u0628\u0627\u0631\u0647 \u0645\u0647\u0627\u0631\u062a\u200c"
    "\u0647\u0627: \u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0631\u0648\u0634 \u0627\u0646\u062c\u0627\u0645 \u06a9\u0627\u0631\u06cc "
    "\u0631\u0627 \u0642\u062f\u0645\u200c\u0628\u0647\u200c\u0642\u062f\u0645 "
    "\u0645\u06cc\u200c\u06af\u0648\u06cc\u062f \u2014 \u0645\u062b\u0644\u0627"
    "\u064b \u0645\u06cc\u200c\u06af\u0648\u06cc\u062f \u00ab\u06cc\u0627\u062f "
    "\u0628\u06af\u06cc\u0631\u00bb \u06cc\u0627 \u00ab\u0627\u0648\u0644... "
    "\u0628\u0639\u062f...\u00bb \u2014 \u0627\u06cc\u0646 \u06cc\u06a9 \u0631"
    "\u0648\u0634 \u0627\u0633\u062a\u060c \u0646\u0647 \u06cc\u06a9 \u0648"
    "\u0627\u0642\u0639\u06cc\u062a \u062f\u0631\u0628\u0627\u0631\u0647 \u062e"
    "\u0648\u062f\u0634\u061b \u067e\u0633 \u0622\u0646 \u0631\u0627 \u062f"
    "\u0631 \u062e\u0627\u0637\u0631\u0647\u200c\u0647\u0627 \u0630\u062e\u06cc"
    "\u0631\u0647 \u0646\u06a9\u0646. \u0647\u0645\u0647 \u0642\u062f\u0645"
    "\u200c\u0647\u0627 \u0631\u0627 \u062c\u0645\u0639 \u06a9\u0646 \u0648 "
    "\u0628\u0627 \u0627\u0628\u0632\u0627\u0631 save_skill \u06cc\u06a9\u200c"
    "\u062c\u0627 \u0630\u062e\u06cc\u0631\u0647 \u06a9\u0646\u061b \u0647\u0631"
    " \u067e\u06cc\u0627\u0645 \u0631\u0627 \u06cc\u06a9 \u0631\u0648\u0634 "
    "\u062c\u062f\u0627 \u0646\u06a9\u0646. \u0627\u06af\u0631 \u0628\u0639"
    "\u062f\u0627\u064b \u0642\u062f\u0645 \u062a\u0627\u0632\u0647\u200c\u0627"
    "\u06cc \u06af\u0641\u062a\u060c \u062a\u0645\u0627\u0645 \u0642\u062f\u0645"
    "\u200c\u0647\u0627\u06cc \u0642\u0628\u0644\u06cc \u0648 \u062c\u062f\u06cc"
    "\u062f \u0631\u0627 \u062f\u0648\u0628\u0627\u0631\u0647 \u0628\u0627 "
    "\u0647\u0645\u0627\u0646 \u0646\u0627\u0645 \u0628\u0627 \u0627\u0628\u0632"
    "\u0627\u0631 save_skill \u0630\u062e\u06cc\u0631\u0647 \u06a9\u0646. \u0647"
    "\u0631\u06af\u0632 \u0628\u062f\u0648\u0646 \u0641\u0631\u0627\u062e\u0648"
    "\u0627\u0646\u06cc \u0627\u0628\u0632\u0627\u0631 save_skill \u0627\u062f"
    "\u0639\u0627 \u0646\u06a9\u0646 \u06a9\u0647 \u0631\u0648\u0634\u06cc "
    "\u0630\u062e\u06cc\u0631\u0647 \u06cc\u0627 \u0627\u0636\u0627\u0641\u0647 "
    "\u0634\u062f\u0647 \u0627\u0633\u062a\u061b \u062a\u0623\u06cc\u06cc\u062f "
    "\u0630\u062e\u06cc\u0631\u0647 \u0641\u0642\u0637 \u067e\u0633 \u0627\u0632"
    " \u0641\u0631\u0627\u062e\u0648\u0627\u0646\u06cc \u0627\u0628\u0632\u0627"
    "\u0631 \u0645\u062c\u0627\u0632 \u0627\u0633\u062a. \u0648\u0642\u062a"
    "\u06cc \u06a9\u0627\u0631\u0628\u0631 \u067e\u0631\u0633\u06cc\u062f \u06a9"
    "\u0627\u0631\u06cc \u0631\u0627 \u0686\u0637\u0648\u0631 \u0627\u0646\u062c"
    "\u0627\u0645 \u062f\u0647\u062f\u060c \u0627\u0648\u0644 \u0628\u0627 "
    "\u0627\u0628\u0632\u0627\u0631 use_skill \u0628\u06af\u0631\u062f\u061b "
    "\u0627\u06af\u0631 \u0631\u0648\u0634\u06cc \u067e\u06cc\u062f\u0627 \u0634"
    "\u062f \u0647\u0645\u0627\u0646 \u0631\u0627 \u062f\u0646\u0628\u0627\u0644"
    " \u06a9\u0646 \u0648 \u0627\u06af\u0631 \u0646\u0647\u060c \u0639\u0627"
    "\u062f\u06cc \u067e\u0627\u0633\u062e \u0628\u062f\u0647."
)


class SkillPromptProvider(MemoryProvider):
    """Supplies the skills usage line to the system prompt.

    The M4 ``contribute_prompt`` hook was declared and never called until
    this milestone. The skills subsystem is its first real contributor: a
    subsystem that wants to add its own sentence to the system prompt. The
    provider has no store, no recall, and no tools of its own, so every
    other lifecycle method is a no-op and only ``contribute_prompt`` returns
    anything. ``Dream`` registers it beside the built-in memory provider, so
    the model is finally told that procedures are saved with ``save_skill``
    and looked up with ``use_skill``.
    """

    def is_available(self) -> bool:
        return True

    def initialize(self) -> None:
        pass

    def recall(
        self, query: str, limit: int = 8, reinforce: bool = False
    ) -> list[Memory]:
        return []

    def list_reminders(self, include_inactive: bool = False) -> list[Reminder]:
        return []

    def contribute_prompt(self, query: str, budget_chars: int) -> tuple[str, list[Any]]:
        del query
        if len(SKILLS_USAGE) > budget_chars:
            return "", []
        return SKILLS_USAGE, []

    def persist(self) -> None:
        pass

    def expose_tools(self) -> list[Any]:
        return []

    def shutdown(self) -> None:
        pass
