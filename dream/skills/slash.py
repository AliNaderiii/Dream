"""Hermes-grade slash invocation with stacking (MEM Stage C).

Every installed skill is a slash command.  Leading tokens of a message
stack up to :data:`MAX_STACK` skills; parsing stops at the first token
that is not an installed skill.  Tokens that look like paths
(``/tmp/scan.pdf``) or contain an extra ``/`` are never swallowed.

The parser is the single implementation used by ``Dream.run`` (the
bridge chat path) and by the CLI session dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dream.memory import normalize_fa
from dream.skills.registry import RESERVED_SLASH_NAMES, find_by_name, load_skills_cached

MAX_STACK = 5

# Gloss: «مهارت فراخوانی‌شده»
_LOADED_LABEL = (
    "\u0645\u0647\u0627\u0631\u062a \u0641\u0631\u0627\u062e\u0648\u0627\u0646\u06cc\u200c\u0634"
    "\u062f\u0647"
)


@dataclass(frozen=True, slots=True)
class SlashStack:
    """Result of parsing a leading skill-slash stack."""

    skills: tuple[Any, ...]
    remainder: str
    raw_tokens: tuple[str, ...]

    @property
    def invoked(self) -> bool:
        return bool(self.skills)


def _is_path_like(token: str) -> bool:
    """True when a leading-slash token must not be treated as a skill.

    ``/tmp/scan.pdf`` contains another slash.  ``C:\\foo`` and tokens with
    a file extension after a slash-dot (``/notes.txt`` is still a legal
    hyphen-less name — only extra separators count) are path-like when
    they carry ``\\`` or a second ``/``.
    """
    if not token.startswith("/"):
        return False
    rest = token[1:]
    if not rest:
        return False
    if "/" in rest or "\\" in rest:
        return True
    # Windows drive: /C: or /C:/...
    if len(rest) >= 2 and rest[1] == ":":
        return True
    return False


def parse_slash_stack(message: str) -> SlashStack:
    """Parse leading skill slashes off ``message``.

    Reserved CLI commands (``/skill``, ``/help``, …) stop the stack so
    they keep their existing meaning.  Unknown ``/foo`` also stops: it
    is not silently eaten.
    """
    tokens = message.split()
    stacked: list[Any] = []
    raw: list[str] = []
    consumed = 0
    # Build a slash lookup once so a 50-skill workspace stays cheap.
    skills, _ = load_skills_cached()
    by_slash: dict[str, Any] = {}
    for skill in skills:
        if skill.slash:
            by_slash[normalize_fa(skill.slash).strip()] = skill
        by_slash.setdefault(normalize_fa(skill.name).strip(), skill)

    for token in tokens:
        if len(stacked) >= MAX_STACK:
            break
        if not token.startswith("/"):
            break
        if _is_path_like(token):
            break
        name = token[1:]
        if not name:
            break
        folded = normalize_fa(name).strip()
        reserved = folded.lower() if folded.isascii() else folded
        if reserved in RESERVED_SLASH_NAMES:
            break
        skill = by_slash.get(folded)
        if skill is None:
            # Try find_by_name for hyphen/space variants of v1 names.
            skill = find_by_name(name)
        if skill is None:
            break
        stacked.append(skill)
        raw.append(token)
        consumed += 1

    remainder = " ".join(tokens[consumed:])
    return SlashStack(tuple(stacked), remainder, tuple(raw))


def format_loaded_skills(stack: SlashStack) -> str:
    """Turn invoked skills into a turn-local user-message suffix.

    Bodies go into the *user* turn, never the system prompt — that is
    the progressive-disclosure contract.  The system catalog stays
    name+description only.
    """
    if not stack.skills:
        return ""
    parts: list[str] = []
    for skill in stack.skills:
        body = skill.body if skill.kind == "skill_md" else skill.body
        parts.append(f"[{_LOADED_LABEL}: {skill.slash or skill.name}]\n{body}")
    return "\n\n".join(parts)


def apply_slash_invocation(message: str) -> tuple[str, SlashStack]:
    """Return ``(model_visible_message, stack)``.

    When nothing is invoked the original message is returned unchanged
    (byte-identical), so existing turns keep their prompt.
    """
    stack = parse_slash_stack(message)
    if not stack.invoked:
        return message, stack
    loaded = format_loaded_skills(stack)
    # Keep the owner's text first so a trailing instruction stays visible.
    return f"{message}\n\n{loaded}", stack
