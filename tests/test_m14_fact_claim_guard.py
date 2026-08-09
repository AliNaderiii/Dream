"""Pins M14's fact save-claim detector: a reply that claims a fact was
remembered or stored is only true when the turn actually wrote a memory row.

What this pins and what evidence justified it:

- On merged main the skill guard covers skills only; the same lie is still
  free for facts. Six replies, none backed by anything, none flagged, three of
  them fact claims: «این را در حافظه ذخیره کردم», «این واقعیت ثبت شد», and
  «یادم می‌ماند که شما مهندس هستید». These tests pin the detector that turns
  the fact half into a property of the finished turn.

- The basis is the outcome, not the attempt: a turn either wrote a memory row
  or it did not. Facts reach the store by two roads — a `remember_fact` call,
  or the silent extraction pass with no tool call at all — so a call-shaped
  guard like M13's would punish the truthful extraction road. The one field
  that separates the roads is `memories_created`, and that is what the guard
  asks about.

- Negation is by design, not word order: the negative prefix attaches to the
  Persian verb, so a denial differs from its claim by whole tokens (نشد،
  نشده، نکردم for the save family; نمی‌آید، نیست، ندارم for the recall family)
  that are never members of the positive sets.

- Normalisation: every Persian constant is written as backslash-u escapes and
  passed through the same `normalize_fa` folding the store uses, so a constant
  written with a hamza or a ZWNJ could not silently fail to match. The check
  is pinned here.

The unit tests below are red by the guard module not existing (import), which
is the honest red for new machinery; the turn-seam behaviour is pinned
separately in test_m14_fact_claim_guard_turn.py so the red names the problem
instead of an import error.
"""

from __future__ import annotations

from dream.claims import (  # type: ignore
    _FACT_MARKERS,
    _FACT_SAVE_STEMS,
    _NON_MEMORY_CONTAINERS,
    _RECALL_PHRASES,
    _RECALL_SOURCE,
    FACT_SAVE_WARNING,
    guard_claims,
    guard_fact_save_claim,
    unsaved_fact_claim,
)
from dream.memory import Memory, _tokenize, normalize_fa
from dream.skills import SKILL_SAVE_WARNING  # for the single-warning pin

# Persian literals as backslash-u escapes (repository convention), with
# plain-Persian glosses.

# Gloss: این را در حافظه ذخیره کردم.
FACT_HAFEZE = (
    "\u0627\u06cc\u0646 \u0631\u0627 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 "
    "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0631\u062f\u0645"
)
# Gloss: این واقعیت ثبت شد.
FACT_SABT = (
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u062b\u0628\u062a \u0634\u062f"
)
# Gloss: یادم می‌ماند که شما مهندس هستید.
FACT_RECALL = (
    "\u06cc\u0627\u062f\u0645 \u0645\u06cc\u200c\u0645\u0627\u0646\u062f \u06a9\u0647 "
    "\u0634\u0645\u0627 \u0645\u0647\u0646\u062f\u0633 \u0647\u0633\u062a\u06cc\u062f"
)
# Gloss: این را به خاطر سپردم.
REPLY_REMEMBER = (
    "\u0627\u06cc\u0646 \u0631\u0627 \u0628\u0647 \u062e\u0627\u0637\u0631 \u0633\u067e\u0631\u062f\u0645"  # noqa: E501
)

FACT_CLAIMS = (FACT_HAFEZE, FACT_SABT, FACT_RECALL, REPLY_REMEMBER)

# Gloss: این واقعیت ثبت نشد. | این را در حافظه ذخیره نکردم. |
#        چیزی در حافظه ذخیره نشده است. | این واقعیت ذخیره نشده است.
SAVE_DENIALS = (
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u062b\u0628\u062a \u0646\u0634\u062f",
    "\u0627\u06cc\u0646 \u0631\u0627 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0646\u06a9\u0631\u062f\u0645",
    "\u0686\u06cc\u0632\u06cc \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a",
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u0630\u062e\u06cc\u0631\u0647 "
    "\u0646\u0634\u062f\u0647 \u0627\u0633\u062a",
)
# Gloss: یادم نمی‌آید که شما مهندس هستید. | به خاطر ندارم. |
#        یادم نیست که این را گفتی. | به یاد ندارم.
RECALL_DENIALS = (
    "\u06cc\u0627\u062f\u0645 \u0646\u0645\u06cc\u200c\u0622\u06cc\u062f \u06a9\u0647 "
    "\u0634\u0645\u0627 \u0645\u0647\u0646\u062f\u0633 \u0647\u0633\u062a\u06cc\u062f",
    "\u0628\u0647 \u062e\u0627\u0637\u0631 \u0646\u062f\u0627\u0631\u0645",
    "\u06cc\u0627\u062f\u0645 \u0646\u06cc\u0633\u062a \u06a9\u0647 \u0627\u06cc\u0646 "
    "\u0631\u0627 \u06af\u0641\u062a\u06cc",
    "\u0628\u0647 \u06cc\u0627\u062f \u0646\u062f\u0627\u0631\u0645",
)
# Gloss: این روش تمدید بیمه ماشین ذخیره شد. — a *skill* claim that the fact
#        guard must leave alone (روش is a skill noun, not a fact marker).
SKILL_CLAIM = (
    "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646 "  # noqa: E501
    "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
)
# Gloss: یادآوری تنظیم شد. | یادآوری تمدید بیمه ثبت شد. — reminder claims,
#        deferred by design (no reminder tool, no reminder guard).
REMINDER_CLAIMS = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f",
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "  # noqa: E501
    "\u062b\u0628\u062a \u0634\u062f",
)
# Gloss: یادداشت ذخیره شد. | این واقعیت را در یادداشت ذخیره کردم. | این را ذخیره کردم.
NON_FACT_SAFES = (
    "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f",
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u0631\u0627 \u062f\u0631 "
    "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a \u0630\u062e\u06cc\u0631\u0647 \u06a9\u0631\u062f\u0645",  # noqa: E501
    "\u0627\u06cc\u0646 \u0631\u0627 \u0630\u062e\u06cc\u0631\u0647 \u06a9\u0631\u062f\u0645",
)
# Gloss: این روش در فایل ذخیره شد و این واقعیت در حافظه ثبت شد. — one sentence
#        that names both a skill-file claim and a fact claim.
MIXED_BOTH = (
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u062f\u0631 \u0641\u0627\u06cc\u0644 \u0630\u062e\u06cc\u0631\u0647 "  # noqa: E501
    "\u0634\u062f \u0648 \u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u062f\u0631 "
    "\u062d\u0627\u0641\u0638\u0647 \u062b\u0628\u062a \u0634\u062f"
)
# Gloss: یادآوری روش تمدید بیمه تنظیم شد. — the brief's reminder/procedure
#        collision sentence.
MIXED_BRIEF = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f "
    "\u0628\u06cc\u0645\u0647 \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f"
)

# Gloss: کاربر مهندس است | سگ کاربر رکس است | کاربر اهل تهران است
MEM_ENGINEER = "کاربر مهندس است"
MEM_PET = "سگ کاربر رکس است"
MEM_CITY = "کاربر اهل تهران است"


def _memory(content: str) -> Memory:
    return Memory(id=1, kind="semantic", content=content, norm=normalize_fa(content))


def test_six_fact_claims_with_no_row_are_flagged():
    """Unbacked fact claims — the three measured ones plus the memorising
    paraphrase — all flag when no memory row was written and none was shown."""
    for reply in FACT_CLAIMS:
        assert unsaved_fact_claim(reply, [], []) is True, (
            f"unbacked fact claim must flag: {reply!r}"
        )


def test_save_claim_backed_by_a_created_row_is_clear():
    """A save claim is confirmed by any memory row the turn actually wrote."""
    assert unsaved_fact_claim(FACT_HAFEZE, [_memory(MEM_PET)], []) is False
    assert unsaved_fact_claim(FACT_SABT, [_memory(MEM_PET)], []) is False
    assert unsaved_fact_claim(REPLY_REMEMBER, [_memory(MEM_PET)], []) is False


def test_recall_claim_backed_by_a_matching_row_or_injected_memory_is_clear():
    """A recall claim («یادم می‌ماند که شما مهندس هستید») is confirmed when the
    subject matches a row written this turn or a memory the model was shown —
    a truthful recall of existing memory is never punished."""
    assert unsaved_fact_claim(FACT_RECALL, [_memory(MEM_ENGINEER)], []) is False
    assert unsaved_fact_claim(FACT_RECALL, [], [_memory(MEM_ENGINEER)]) is False
    # A non-matching row (the pet) does not back a claim about being an engineer.
    assert unsaved_fact_claim(FACT_RECALL, [_memory(MEM_PET)], []) is True


def test_skill_and_reminder_claims_are_not_fact_claims():
    """Scoping: a skill claim (skill noun) and a reminder claim (deferred) are
    not the fact guard's subject, even when unbacked."""
    assert unsaved_fact_claim(SKILL_CLAIM, [], []) is False
    for reply in REMINDER_CLAIMS:
        assert unsaved_fact_claim(reply, [], []) is False, (
            f"reminder claim must be left to the deferred tool, not the fact guard: {reply!r}"
        )


def test_note_and_bare_saves_are_not_fact_claims():
    """Scoping: a note save and a bare save with no fact/memory marker are not
    fact claims — flagging them would punish truthful non-memory replies."""
    for reply in NON_FACT_SAFES:
        assert unsaved_fact_claim(reply, [], []) is False, (
            f"non-memory save must never flag: {reply!r}"
        )


def test_save_denials_are_never_flagged_by_design():
    """The save family's four denials differ from their claims by whole tokens
    (نشد، نکردم، نشده) that are never members of the positive past-verb set."""
    for reply in SAVE_DENIALS:
        assert unsaved_fact_claim(reply, [], []) is False, (
            f"save denial must never flag: {reply!r}"
        )


def test_recall_denials_are_never_flagged_by_design():
    """The recall family's four denials (یادم نمی‌آید، به خاطر ندارم، یادم نیست،
    به یاد ندارم) are not members of the closed positive recall-phrase set."""
    for reply in RECALL_DENIALS:
        assert unsaved_fact_claim(reply, [], []) is False, (
            f"recall denial must never flag: {reply!r}"
        )


def test_no_positive_verb_form_is_a_negative_form():
    """The design invariant behind save negation: a denial token can never be
    read as a completed positive verb by the detector."""
    from dream.skills import _NEGATIVE_VERBS, _PAST_VERBS  # type: ignore

    assert _NEGATIVE_VERBS.isdisjoint(_PAST_VERBS)


def test_normalisation_check_on_every_new_persian_constant():
    """Every new Persian constant is stable under the store's own folding, so
    a hamza or ZWNJ spelling could not silently fail to match. The detector
    builds its comparison sets by passing these constants through the same
    `normalize_fa` / tokenisation pipeline the store uses."""
    constants = {
        "\u0630\u062e\u06cc\u0631\u0647", "\u062b\u0628\u062a", "\u0636\u0628\u0637",
        "\u0648\u0627\u0642\u0639\u06cc\u062a", "\u062d\u0627\u0641\u0638\u0647",
        "\u062e\u0627\u0637\u0631\u0647", "\u0646\u06a9\u062a\u0647",
        "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a", "\u0627\u06cc\u0645\u06cc\u0644",
        "\u0641\u0627\u06cc\u0644",
    }
    for constant in constants:
        assert normalize_fa(constant) == constant, (
            f"Persian constant must already be canonical under normalize_fa: {constant!r}"
        )
    # The recall phrases are built through tokenisation: every source phrase is
    # present as its normalized token tuple, and the hamza-bearing denial
    # «یادم نمی‌آید» folds to a tuple that is not a positive member.
    for phrase in _RECALL_SOURCE:
        assert tuple(_tokenize(phrase)) in _RECALL_PHRASES, (
            f"recall phrase must survive the store's folding: {phrase!r}"
        )
    assert tuple(_tokenize("\u06cc\u0627\u062f\u0645 \u0646\u0645\u06cc\u200c\u0622\u06cc\u062f")) \
        not in _RECALL_PHRASES


def test_guard_fact_save_claim_appends_only_on_unconfirmed():
    """The guard appends the warning exactly when a claim is unconfirmed, and
    leaves a backed reply and an abandoned extraction byte for byte."""
    unbacked = guard_fact_save_claim(FACT_HAFEZE, [], [], "no_facts")
    assert unbacked == FACT_HAFEZE + FACT_SAVE_WARNING
    backed = guard_fact_save_claim(FACT_HAFEZE, [_memory(MEM_PET)], [], "no_facts")
    assert backed == FACT_HAFEZE
    abandoned = guard_fact_save_claim(FACT_HAFEZE, [], [], "abandoned")
    assert abandoned == FACT_HAFEZE


def test_guard_claims_never_appends_two_warnings():
    """Ownership: the skill guard is consulted first, so a reply that names
    both a skill-file claim and a fact claim yields exactly one warning, never
    two. The reminder/procedure collision fires neither guard and stays put."""
    mixed = guard_claims(MIXED_BOTH, [], [], [], "no_facts")
    assert mixed == MIXED_BOTH + SKILL_SAVE_WARNING
    assert FACT_SAVE_WARNING not in mixed
    brief = guard_claims(MIXED_BRIEF, [], [], [], "no_facts")
    assert brief == MIXED_BRIEF


def test_marker_sets_are_nonempty_and_deliberate():
    """The detection tables are populated (not accidentally empty) and the
    reminder word یادآوری is deliberately excluded from the memory markers so
    a reminder claim is never misread as a fact claim."""
    assert _FACT_SAVE_STEMS
    assert _FACT_MARKERS
    assert _NON_MEMORY_CONTAINERS
    assert "\u06cc\u0627\u062f" not in _FACT_MARKERS  # یاد
