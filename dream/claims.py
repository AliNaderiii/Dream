"""Save-claim guards for durable writes beyond skills.

M13 shipped a guard that makes a *skill* save claim a property of the turn:
a reply that says a procedure was saved is only true when a ``save_skill``
call actually completed. The same lie was still free in two other places,
both measured on merged main: a reply can claim a *fact* was remembered or
stored when nothing was written, and a reply can claim a *reminder* was set.

This milestone closes the fact half and deliberately declines the reminder
half. The reason the two are handled differently is measured, not assumed:

- Facts reach the store by two roads. The model may call ``remember_fact``,
  or the silent extraction pass may write the fact after the reply is
  composed with no tool call at all. A guard shaped like M13's — ask whether
  a ``remember_fact`` call completed — would call a truthful extraction-road
  reply a lie, because the call list is empty. The turn already records the
  outcome, and one field separates the two roads: ``memories_created``. The
  fact guard therefore asks whether the turn actually wrote a memory row,
  not whether a tool was named.

- Reminders have no tool at all. The registry lists no reminder tool, so a
  model cannot set a reminder even if it wants to; reminders are created only
  by the owner's own ``/remind`` command. A reply claiming a reminder was set
  is therefore false every time — but the honest fix is to give the model the
  tool it is already pretending to have, and that tool touches the tool
  module, which is out of budget here. A guard would risk punishing truthful
  replies that describe an *existing* reminder (visible to the model in the
  reminder prompt section), so no reminder guard ships. It is deferred with
  the reasoning recorded in the status document.

The fact guard's basis is the outcome: a turn either wrote a memory row or
it did not. The one timing boundary is the abandoned extraction pass — a
truthful reply can be composed before its own row exists because the pass
runs on a worker with a wall-clock budget. When extraction is abandoned the
guard does nothing, because warning then would punish a truthful reply whose
row is still in flight.

Every Persian constant in this module is written as backslash-u escapes and
passed through the same ``normalize_fa`` / tokenisation pipeline the store
uses before it is trusted, so a constant written with a hamza or a ZWNJ folds
to exactly the form the store would store (checked in the tests).
"""

from __future__ import annotations

from typing import Any

from dream.extraction import STATUS_ABANDONED
from dream.memory import _tokenize, normalize_fa
from dream.skills import (
    _PAST_PERFECT_MARKERS,
    _PAST_REFERENCE,
    _PAST_VERBS,
    _QUESTION_WORDS,
    _content_stems,
    _stem_match,
    guard_skill_save_claim,
)

__all__ = [
    "FACT_SAVE_WARNING",
    "guard_claims",
    "guard_fact_save_claim",
    "unsaved_fact_claim",
]

# How far back from a save stem to hunt for a fact/memory marker, matching the
# M13 skill claim window.
_CLAIM_WINDOW = 10

# Save stems that make a *fact* claim when they land on a memory/fact context
# (a fact noun, a memory noun, or «به خاطر»). Gloss: ذخیره، ثبت، ضبط.
_FACT_SAVE_STEMS: frozenset[str] = frozenset(
    normalize_fa(word)
    for word in (
        "\u0630\u062e\u06cc\u0631\u0647",  # ذخیره
        "\u062b\u0628\u062a",              # ثبت
        "\u0636\u0628\u0637",              # ضبط
    )
)

# Fact nouns: a save word landing on one of these claims a *fact* write, not a
# note or a skill. Gloss: واقعیت، موضوع، نکته، مطلب، چیز.
_FACT_NOUNS: frozenset[str] = frozenset(
    normalize_fa(word)
    for word in (
        "\u0648\u0627\u0642\u0639\u06cc\u062a",  # واقعیت
        "\u0645\u0648\u0636\u0648\u0639",      # موضوع
        "\u0646\u06a9\u062a\u0647",            # نکته
        "\u0645\u0637\u0644\u0628",            # مطلب
        "\u0686\u06cc\u0632",                  # چیز
    )
)

# Memory containers: the store these claims say they wrote to. Gloss:
# حافظه، خاطره، خاطرات، ذهن. «یاد» is deliberately absent: «یادآوری»
# (reminder) contains it, and reminder claims are not fact claims.
_MEMORY_NOUNS: frozenset[str] = frozenset(
    normalize_fa(word)
    for word in (
        "\u062d\u0627\u0641\u0638\u0647",      # حافظه
        "\u062e\u0627\u0637\u0631\u0647",      # خاطره
        "\u062e\u0627\u0637\u0631\u0627\u062a",  # خاطرات
        "\u0630\u0647\u0646",                  # ذهن
    )
)

# Combined marker set for the save family: a fact noun, a memory noun, or the
# «به خاطر» marker of a memorising claim.
_FACT_MARKERS: frozenset[str] = (
    _FACT_NOUNS | _MEMORY_NOUNS | {normalize_fa("\u062e\u0627\u0637\u0631")}  # خاطر
)

# Containers that are not memory: a save landing on one of these is not a fact
# claim, even when a fact noun is present («این واقعیت را در یادداشت ذخیره
# کردم» is a note save, not a memory write). Gloss: یادداشت، ایمیل، فایل.
_NON_MEMORY_CONTAINERS: frozenset[str] = frozenset(
    normalize_fa(word)
    for word in (
        "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a",  # یادداشت
        "\u0627\u06cc\u0645\u06cc\u0644",            # ایمیل
        "\u0641\u0627\u06cc\u0644",                  # فایل
    )
)

# Positive "I remember / committed to memory" phrases. Written with a ZWNJ in
# «میماند/میمونه» where standard Persian uses one, plus the no-ZWNJ spellings,
# because a model may emit either and both must match after the store folds
# ZWNJ to a space. Each phrase is tokenised through the store's own pipeline
# when the set is built, so the hamza/ZWNJ trap cannot bite here. The denial
# forms (یادم نمیآید، یادم نیست، به خاطر ندارم، به یاد ندارم) are deliberately
# not members; a test pins the two sides apart.
_RECALL_SOURCE: tuple[str, ...] = (
    "\u06cc\u0627\u062f\u0645 \u0645\u06cc\u200c\u0645\u0627\u0646\u062f",  # یادم می‌ماند
    "\u06cc\u0627\u062f\u0645 \u0645\u06cc\u0645\u0627\u0646\u062f",  # یادم میماند (no ZWNJ)
    "\u06cc\u0627\u062f\u0645 \u0645\u06cc\u200c\u0645\u0648\u0646\u0647",  # یادم می‌مونه
    "\u06cc\u0627\u062f\u0645 \u0645\u06cc\u0645\u0648\u0646\u0647",  # یادم میمونه (no ZWNJ)
    "\u06cc\u0627\u062f\u0645 \u0645\u06cc\u0627\u062f",  # یادم میاد
    "\u06cc\u0627\u062f\u0645 \u0627\u0633\u062a",  # یادم است
    "\u06cc\u0627\u062f\u0645 \u0647\u0633\u062a",  # یادم هست
    "\u0628\u0647 \u06cc\u0627\u062f \u062f\u0627\u0631\u0645",  # به یاد دارم
    "\u0628\u0647 \u062e\u0627\u0637\u0631 \u062f\u0627\u0631\u0645",  # به خاطر دارم
    "\u0628\u0647 \u062e\u0627\u0637\u0631 \u0633\u067e\u0631\u062f\u0645",  # به خاطر سپردم
    "\u0628\u0647 \u062e\u0627\u0637\u0631 \u0633\u067e\u0631\u062f\u0647 \u0634\u062f",  # به خاطر سپرده شد  # noqa: E501
)
_RECALL_PHRASES: frozenset[tuple[str, ...]] = frozenset(
    tuple(_tokenize(phrase)) for phrase in _RECALL_SOURCE
)

# The warning the owner sees when a fact claim is unconfirmed. Gloss:
# «توجه: ادعای ذخیره‌شدن این واقعیت تایید نشده است؛ چیزی در حافظه ذخیره
# نشده است.»
FACT_SAVE_WARNING = (
    "\n\n"
    "\u062a\u0648\u062c\u0647: "
    "\u0627\u062f\u0639\u0627\u06cc \u0630\u062e\u06cc\u0631\u0647\u200c\u0634\u062f\u0646 "
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a "
    "\u062a\u0627\u06cc\u06cc\u062f \u0646\u0634\u062f\u0647 \u0627\u0633\u062a\u061b "
    "\u0686\u06cc\u0632\u06cc \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
)


def _claims_fact_save(reply: str) -> bool:
    """Whether the reply claims a *fact* was written to memory.

    A save stem (ذخیره/ثبت/ضبط) completed by a positive past verb, with a
    fact noun, a memory noun, or «به خاطر» inside the claim window, and none
    of the vetoes (question, past reference, relative clause, a non-memory
    container, or a past-perfect marker) firing. The negative verbs (نشد،
    نشده، نکردم، ...) are never members of the positive past-verb set, so
    negation is a design property, not a word-order accident.
    """
    tokens = _tokenize(reply)
    for index, token in enumerate(tokens):
        if token not in _FACT_SAVE_STEMS:
            continue
        verb = tokens[index + 1] if index + 1 < len(tokens) else ""
        if verb not in _PAST_VERBS:
            continue
        before = tokens[max(0, index - _CLAIM_WINDOW):index]
        if not any(marker in before for marker in _FACT_MARKERS):
            continue
        if _fact_vetoed(before, tokens[index + 1 : index + 3]):
            continue
        return True
    return False


def _fact_vetoed(before: list[str], after: list[str]) -> bool:
    """Whether the context around a save complex marks it as no fact claim."""
    if any(word in before for word in _QUESTION_WORDS):
        return True
    if any(word in before for word in _PAST_REFERENCE):
        return True
    if before and before[-1] == normalize_fa("\u06a9\u0647"):  # که
        return True
    if any(word in before[-3:] for word in _NON_MEMORY_CONTAINERS):
        return True
    if any(word in after for word in _PAST_PERFECT_MARKERS):
        return True
    return False


def _claims_fact_recall(reply: str) -> tuple[bool, set[str]]:
    """Whether the reply claims memory of something, and the claimed content.

    Returns ``(found, content_stems)`` where ``content_stems`` is the
    substantive subject matter after the recall phrase (empty for a generic
    «یادم می‌ماند»). The positive recall phrases are a closed set; denials
    (یادم نمی‌آید، یادم نیست، به خاطر ندارم، به یاد ندارم) are not members.
    """
    tokens = _tokenize(reply)
    for index in range(len(tokens)):
        for phrase in _RECALL_PHRASES:
            if tokens[index : index + len(phrase)] == list(phrase):
                content = _content_stems(" ".join(tokens[index + len(phrase):]))
                return True, content
    return False, set()


def _memory_stems(memory: Any) -> set[str]:
    """Content stems of one memory row's stored text."""
    return _content_stems(getattr(memory, "content", ""))


def _matches(content: set[str], memories: list[Any]) -> bool:
    """Whether any memory shares a content stem with the claimed subject."""
    for memory in memories or []:
        memory_stems = _memory_stems(memory)
        if any(
            _stem_match(claimed, stored)
            for claimed in content
            for stored in memory_stems
        ):
            return True
    return False


def unsaved_fact_claim(
    reply: str, memories_created: list[Any], memories_injected: list[Any] | None
) -> bool:
    """Whether a reply claims a fact write that no memory row backs.

    The basis is the outcome, not the attempt: a turn either wrote a memory
    row or it did not. A save claim («این را در حافظه ذخیره کردم») is
    unconfirmed when no row was written this turn. A recall claim («یادم
    می‌ماند که شما مهندس هستید») is confirmed when the claimed subject
    matches a row written this turn *or* a memory the model was shown this
    turn (a truthful recall of existing memory must never be punished).
    """
    memories_created = memories_created or []
    memories_injected = memories_injected or []

    if _claims_fact_save(reply):
        return not bool(memories_created)

    recall_found, content = _claims_fact_recall(reply)
    if not recall_found:
        return False
    if content:
        if _matches(content, memories_created) or _matches(content, memories_injected):
            return False
        return True
    return not bool(memories_created)


def guard_fact_save_claim(
    reply: str,
    memories_created: list[Any],
    memories_injected: list[Any] | None,
    extraction_status: str,
) -> str:
    """Return the reply, appending a Persian warning when its fact claim is
    unconfirmed. A truthful reply — a claim backed by a memory row written
    this turn, or a recall backed by a memory the model was shown — is
    returned byte for byte.

    On an abandoned extraction the reply is returned unchanged: a truthful
    reply can be composed before its own row exists because the extraction
    pass runs on a worker with a wall-clock budget, so warning then would
    punish a truthful reply whose row is still in flight.
    """
    if extraction_status == STATUS_ABANDONED:
        return reply
    if unsaved_fact_claim(reply, memories_created, memories_injected):
        return reply + FACT_SAVE_WARNING
    return reply


def guard_claims(
    reply: str,
    tool_calls: list[dict[str, Any]],
    memories_created: list[Any],
    memories_injected: list[Any] | None,
    extraction_status: str,
) -> str:
    """Apply every claim guard, appending at most one warning.

    Ownership rule: the skill guard is consulted first; if it fires, its
    warning is the single warning and the fact guard is not reached. Only
    when the skill guard passes does the fact guard run. The owner therefore
    never reads two warnings on one reply. The reminder/procedure collision
    the brief names fires neither guard (reminders are a deferred tool), so
    that sentence reaches the owner unchanged.
    """
    skill_guarded = guard_skill_save_claim(reply, tool_calls)
    if skill_guarded != reply:
        return skill_guarded
    return guard_fact_save_claim(
        reply, memories_created, memories_injected, extraction_status
    )
