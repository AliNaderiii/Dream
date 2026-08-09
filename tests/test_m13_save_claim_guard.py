"""Pins M13's save-claim detector: a reply that claims a skill was saved is
only true when a save_skill call actually completed in the same turn.

What this pins and what evidence justified it:

- The owner was once told the second half of a procedure was added and heard
  all three steps recited while the file on disk still held one step. The
  rule against claiming a save without calling save_skill existed only as a
  sentence in the system prompt; a search of the conversation module found
  no code behind it. These tests pin the detector that turns the sentence
  into a property of every finished turn.

- The basis is the outcome, not the attempt: a turn either changed a skill
  file or it did not. A save_skill call counts only when it was allowed and
  its result carries ``status: ok``. The four holes found in the candidate
  detector are each pinned here: a blocked call (hole one), the wrong skill
  (hole two), a paraphrase with no save word (hole three), and Persian
  negation (hole four) — the last by design, because the negative prefix
  attaches to the verb (ذخیره شد vs ذخیره نشد), so the detector matches
  whole tokens against a closed set of positive past forms and the negative
  forms are never members.

- Scoping was measured, not guessed: a bare save-word pattern raises false
  positives on note and fact replies (those tools legitimately say something
  was saved), so a skill noun (روش، مهارت، قدم، مرحله، ...) is required
  inside the claim window. Offers and questions («میخواهم ذخیره کنم»,
  «آیا ذخیره شد؟») are excluded by construction: only completed past and
  perfective verb forms are claim verbs, and a question word before the
  claim vetoes it.

Every test here was observed failing against unchanged source (the guard
functions did not exist) and green after the source change; the end-to-end
behaviour is pinned separately in test_m13_save_claim_guard_turn.py so the
red names the problem instead of an import error.
"""

from __future__ import annotations

from dream.skills import (
    _NEGATIVE_VERBS,  # type: ignore
    _PAST_VERBS,  # type: ignore
    unsaved_skill_claim,
)

# Persian literals as backslash-u escapes (repository convention), with
# plain-Persian glosses.
# Gloss: روش تمدید بیمه ماشین ذخیره شد.
CLAIM_INSURANCE = (
    "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "
    "\u0645\u0627\u0634\u06cc\u0646 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
)
# Gloss: قدم دوم اضافه شد و هر سه قدم ثبت شد.
CLAIM_STEPS = (
    "\u0642\u062f\u0645 \u062f\u0648\u0645 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f "
    "\u0648 \u0647\u0631 \u0633\u0647 \u0642\u062f\u0645 \u062b\u0628\u062a \u0634\u062f."
)
# Gloss: این مهارت را ذخیره کردم.
CLAIM_SKILL = (
    "\u0627\u06cc\u0646 \u0645\u0647\u0627\u0631\u062a \u0631\u0627 "
    "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0631\u062f\u0645."
)
# Gloss: مهارت چای دم کردن ذخیره شده است.
CLAIM_TEA = (
    "\u0645\u0647\u0627\u0631\u062a \u0686\u0627\u06cc \u062f\u0645 \u06a9\u0631\u062f\u0646 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0647 \u0627\u0633\u062a."
)
# Gloss: همه مراحل در فایل ذخیره شد.
CLAIM_STAGES = (
    "\u0647\u0645\u0647 \u0645\u0631\u0627\u062d\u0644 \u062f\u0631 \u0641\u0627\u06cc\u0644 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
)
# Gloss: قدم اضافه شد: ۱. پیدا کردن بیمه‌نامه ۲. برداشتن کارت ماشین ۳. رفتن به نمایندگی
CLAIM_RECITAL = (
    "\u0642\u062f\u0645 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f: "
    "\u06f1. \u067e\u06cc\u062f\u0627 \u06a9\u0631\u062f\u0646 \u0628\u06cc\u0645\u0647\u200c\u0646\u0627\u0645\u0647 "  # noqa: E501
    "\u06f2. \u0628\u0631\u062f\u0627\u0634\u062a\u0646 \u06a9\u0627\u0631\u062a \u0645\u0627\u0634\u06cc\u0646 "  # noqa: E501
    "\u06f3. \u0631\u0641\u062a\u0646 \u0628\u0647 \u0646\u0645\u0627\u06cc\u0646\u062f\u06af\u06cc"
)
CLAIM_PHRASINGS = (
    CLAIM_INSURANCE,
    CLAIM_STEPS,
    CLAIM_SKILL,
    CLAIM_TEA,
    CLAIM_STAGES,
    CLAIM_RECITAL,
)

# Gloss: تمدید بیمه ماشین | چای دم کردن | تمدید بیمه
NAME_INSURANCE = (  # noqa: E501
    "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
)
NAME_TEA = "\u0686\u0627\u06cc \u062f\u0645 \u06a9\u0631\u062f\u0646"
NAME_INSURANCE_PARTIAL = "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647"

# Gloss: این روش ذخیره نشد. | روش تمدید بیمه ماشین ذخیره نشده است. |
#        قدم اضافه نشد. | من هیچ روشی را ذخیره نکردم. | روش هنوز در فایل نیست. |
#        مهارت ثبت نشده است. | این روش قبلا ذخیره شده است. | این روش ذخیره شده بود.
DENIALS = (
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0630\u062e\u06cc\u0631\u0647 \u0646\u0634\u062f.",
    "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646 "  # noqa: E501
    "\u0630\u062e\u06cc\u0631\u0647 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.",
    "\u0642\u062f\u0645 \u0627\u0636\u0627\u0641\u0647 \u0646\u0634\u062f.",
    "\u0645\u0646 \u0647\u06cc\u0686 \u0631\u0648\u0634\u06cc \u0631\u0627 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0646\u06a9\u0631\u062f\u0645.",
    "\u0631\u0648\u0634 \u0647\u0646\u0648\u0632 \u062f\u0631 \u0641\u0627\u06cc\u0644 \u0646\u06cc\u0633\u062a.",  # noqa: E501
    "\u0645\u0647\u0627\u0631\u062a \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.",  # noqa: E501
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0642\u0628\u0644\u0627 \u0630\u062e\u06cc\u0631\u0647 "
    "\u0634\u062f\u0647 \u0627\u0633\u062a.",
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0647 \u0628\u0648\u062f.",  # noqa: E501
)

# Replies that must never be flagged: notes, facts, reminders, reads, offers,
# questions, non-skill containers, and bare verbs without a file.
# Gloss: یادداشت ذخیره شد. | این واقعیت ذخیره شد و به خاطر سپرده شد. |
#        یادآوری تنظیم شد. | این روش را از فایل مهارت‌ها پیدا کردم. |
#        روش در فایل مهارت موجود است. | می‌خواهم این روش را ذخیره کنم. |
#        آیا روش ذخیره شد؟ | مهارت را ذخیره کنم؟ | این روش حالا در فایل است. |
#        روش را از فایل دریافت کردم. | این روش را در یادداشت ذخیره کردم. |
#        این روش را در حافظه ذخیره کردم. | این روش را نوشتم. |
#        این روش را در یادداشت نوشتم.
SAFE_REPLIES = (
    "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f.",
    "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f "  # noqa: E501
    "\u0648 \u0628\u0647 \u062e\u0627\u0637\u0631 \u0633\u067e\u0631\u062f\u0647 \u0634\u062f.",
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f.",
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0631\u0627 \u0627\u0632 \u0641\u0627\u06cc\u0644 "
    "\u0645\u0647\u0627\u0631\u062a\u200c\u0647\u0627 \u067e\u06cc\u062f\u0627 \u06a9\u0631\u062f\u0645.",  # noqa: E501
    "\u0631\u0648\u0634 \u062f\u0631 \u0641\u0627\u06cc\u0644 \u0645\u0647\u0627\u0631\u062a "
    "\u0645\u0648\u062c\u0648\u062f \u0627\u0633\u062a.",
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645 \u0627\u06cc\u0646 \u0631\u0648\u0634 \u0631\u0627 "  # noqa: E501
    "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0646\u0645.",
    "\u0622\u06cc\u0627 \u0631\u0648\u0634 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u061f",
    "\u0645\u0647\u0627\u0631\u062a \u0631\u0627 \u0630\u062e\u06cc\u0631\u0647 \u06a9\u0646\u0645\u061f",  # noqa: E501
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u062d\u0627\u0644\u0627 \u062f\u0631 \u0641\u0627\u06cc\u0644 "  # noqa: E501
    "\u0627\u0633\u062a.",
    "\u0631\u0648\u0634 \u0631\u0627 \u0627\u0632 \u0641\u0627\u06cc\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a "  # noqa: E501
    "\u06a9\u0631\u062f\u0645.",
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0631\u0627 \u062f\u0631 \u06cc\u0627\u062f\u062f\u0627\u0634\u062a "  # noqa: E501
    "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0631\u062f\u0645.",
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0631\u0627 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 "  # noqa: E501
    "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0631\u062f\u0645.",
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0631\u0627 \u0646\u0648\u0634\u062a\u0645.",
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0631\u0627 \u062f\u0631 \u06cc\u0627\u062f\u062f\u0627\u0634\u062a "  # noqa: E501
    "\u0646\u0648\u0634\u062a\u0645.",
)

# Gloss: روش را دریافت کردم و حالا در فایل است. | این روش را در فایل نوشتم. |
#        روش تمدید بیمه ماشین به فایل اضافه شده است.
PARAPHRASES = (
    "\u0631\u0648\u0634 \u0631\u0627 \u062f\u0631\u06cc\u0627\u0641\u062a \u06a9\u0631\u062f\u0645 "
    "\u0648 \u062d\u0627\u0644\u0627 \u062f\u0631 \u0641\u0627\u06cc\u0644 \u0627\u0633\u062a.",
    "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u0631\u0627 \u062f\u0631 \u0641\u0627\u06cc\u0644 "
    "\u0646\u0648\u0634\u062a\u0645.",
    "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646 "  # noqa: E501
    "\u0628\u0647 \u0641\u0627\u06cc\u0644 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f\u0647 \u0627\u0633\u062a.",  # noqa: E501
)


def _ok_save(name: str = NAME_INSURANCE) -> list[dict]:
    return [
        {
            "name": "save_skill",
            "arguments": {"name": name, "description": "d", "steps": ["s"]},
            "allowed": True,
            "result": '{"status": "ok", "result": {"filename": "skills/x.txt", "status": "created"}}',  # noqa: E501
        }
    ]


def _blocked_save(name: str = NAME_INSURANCE) -> list[dict]:
    return [
        {
            "name": "save_skill",
            "arguments": {"name": name, "description": "d", "steps": ["s"]},
            "allowed": False,
            "result": '{"blocked": true, "reason": "guarded tool denied by approver"}',
        }
    ]


def _failed_save() -> list[dict]:
    return [
        {
            "name": "save_skill",
            "arguments": {"name": NAME_INSURANCE, "description": "d", "steps": []},
            "allowed": True,
            "result": (
                '{"status": "error", "error": {"type": "ValueError", '
                '"message": "Tool call failed: save_skill() raised ValueError"}}'
            ),
        }
    ]


def test_five_real_claim_phrasings_without_a_save_are_flagged():
    """The five measured claim phrasings, no save call: every one flags."""
    for reply in CLAIM_PHRASINGS:
        assert unsaved_skill_claim(reply, []) is True, (
            f"claim without a save must flag: {reply!r}"
        )


def test_same_phrasings_with_a_completed_save_are_clear():
    """The same phrasings with a completed save_skill call: none flag."""
    assert unsaved_skill_claim(CLAIM_INSURANCE, _ok_save(NAME_INSURANCE)) is False
    assert unsaved_skill_claim(CLAIM_STEPS, _ok_save(NAME_INSURANCE)) is False
    assert unsaved_skill_claim(CLAIM_SKILL, _ok_save(NAME_INSURANCE)) is False
    assert unsaved_skill_claim(CLAIM_TEA, _ok_save(NAME_TEA)) is False
    assert unsaved_skill_claim(CLAIM_STAGES, _ok_save(NAME_INSURANCE)) is False
    assert unsaved_skill_claim(CLAIM_RECITAL, _ok_save(NAME_INSURANCE)) is False


def test_note_fact_reminder_read_offer_question_are_never_flagged():
    """Scoping: only a skill save claims; notes, facts, reminders, reads,
    offers, and questions stay silent even with no save call."""
    for reply in SAFE_REPLIES:
        assert unsaved_skill_claim(reply, []) is False, (
            f"non-claim must never flag: {reply!r}"
        )


def test_blocked_call_still_counts_as_no_save():
    """Hole one closed: a blocked save_skill call does not back a claim."""
    assert unsaved_skill_claim(CLAIM_INSURANCE, _blocked_save()) is True
    assert unsaved_skill_claim(CLAIM_STEPS, _blocked_save()) is True


def test_failed_save_call_still_counts_as_no_save():
    """Hole one closed: a call whose write errored does not back a claim."""
    assert unsaved_skill_claim(CLAIM_INSURANCE, _failed_save()) is True


def test_wrong_skill_does_not_back_a_claim():
    """Hole two closed: a tea recipe does not satisfy an insurance claim."""
    assert unsaved_skill_claim(CLAIM_INSURANCE, _ok_save(NAME_TEA)) is True
    # Matching and partial-overlap names do satisfy the claim.
    assert unsaved_skill_claim(CLAIM_INSURANCE, _ok_save(NAME_INSURANCE)) is False
    assert unsaved_skill_claim(CLAIM_INSURANCE, _ok_save(NAME_INSURANCE_PARTIAL)) is False


def test_paraphrase_without_a_save_word_is_flagged():
    """Hole three closed: «دریافت و در فایل» claims a write without ذخیره."""
    for reply in PARAPHRASES:
        assert unsaved_skill_claim(reply, []) is True, (
            f"paraphrase claim must flag: {reply!r}"
        )


def test_persian_denials_are_never_flagged_by_design():
    """Hole four closed by design, not by word order: the negative prefix
    attaches to the Persian verb, so a denial differs from its claim by whole
    tokens (نشد، نشده، نکردم، نیست) that are never members of the positive
    past-verb set the detector matches against."""
    for reply in DENIALS:
        assert unsaved_skill_claim(reply, []) is False, (
            f"denial must never flag: {reply!r}"
        )


def test_negative_verb_set_is_disjoint_from_the_positive_set():
    """The design invariant behind hole four: no denial form can ever be
    read as a completed positive verb by the detector."""
    assert _NEGATIVE_VERBS.isdisjoint(_PAST_VERBS)
    assert "\u0646\u0634\u062f" in _NEGATIVE_VERBS  # نشد
    assert "\u0646\u0634\u062f" not in _PAST_VERBS
    assert "\u0634\u062f\u0647" in _PAST_VERBS  # شده
