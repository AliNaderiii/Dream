"""Pin M17 plural marker defect in skill save-claim guard.

What this pins and what evidence justified it:

- M16 taught suite to detect conditional assertions and allowlisted the
  single offender in test_skill_step_coercion.py. M17 repairs that test.
- While measuring replacement, shipped skill guard was called on the very
  phrase the dead assertion was written for, where save DID happen. It
  should be silent, it is not.
  reply: Persian for "steps were saved", plural with ZWNJ
  turn: one completed save of insurance procedure
  guard: flags it
- Root cause: memory.py folds ZWNJ to space, correct and deliberate.
  Persian plural with joiner becomes two tokens: noun and bare marker "ها".
  Guard reads tokens between skill noun and save word as claimed name.
  For plural that span is marker alone, shares no stem with saved name, so
  guard concludes different procedure and warns.
- Measured eight replies, truthful, backed by completed save:
    plural step joiner, plural step other verb, plural skill,
    plural procedure, plural stage, plural step spaced -> WARNED before fix
    explicit name, singular generic -> silent
  Six of eight. Every Persian plural with that marker turns truthful
  confirmation into warning.
- Fix must treat grammatical affix as not content. Veto: fix that handles
  one affix and not its siblings is not a fix. This module enumerates
  affixes covered and those not covered.
- Also pins: wrong-skill still warned, fact guard does not share defect.

Evidence: eight-reply table before and after fix in PR, break and restore.
"""

from dream.claims import unsaved_fact_claim
from dream.skills import guard_skill_save_claim, unsaved_skill_claim

NAME_INSURANCE = (
    "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
)
NAME_TEA = "\u0686\u0627\u06cc \u062f\u0645 \u06a9\u0631\u062f\u0646"


def _ok_save(name=NAME_INSURANCE):
    return [
        {
            "name": "save_skill",
            "arguments": {"name": name, "description": "d", "steps": ["s"]},
            "allowed": True,
            "result": (
                '{"status": "ok", "result": {"filename": "skills/x.txt", '
                '"status": "created"}}'
            ),
        }
    ]


# Eight replies from brief, all truthful, backed by completed save
REPLIES = {
    "plural_step_joiner": (
        "\u0642\u062f\u0645\u200c\u0647\u0627 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0646\u062f"  # noqa: E501
    ),
    "plural_step_joiner_other_verb": (
        "\u0642\u062f\u0645\u200c\u0647\u0627 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f\u0646\u062f"  # noqa: E501
    ),
    "plural_skill": (
        "\u0645\u0647\u0627\u0631\u062a\u200c\u0647\u0627 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f"  # noqa: E501
    ),
    "plural_procedure": (
        "\u0631\u0648\u0634\u200c\u0647\u0627 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f"
    ),
    "plural_stage": (
        "\u0645\u0631\u062d\u0644\u0647\u200c\u0647\u0627 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f"  # noqa: E501
    ),
    "plural_step_spaced": (
        "\u0642\u062f\u0645 \u0647\u0627 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0646\u062f"
    ),
    "explicit_name": (
        "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "
        "\u0645\u0627\u0634\u06cc\u0646 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
    ),
    "singular_generic": "\u0642\u062f\u0645 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f.",
}


def test_truthful_plural_confirmations_are_silent_after_fix():
    """Six plural forms were WARNED before M17; after fix silent."""
    for key in [
        "plural_step_joiner",
        "plural_step_joiner_other_verb",
        "plural_skill",
        "plural_procedure",
        "plural_stage",
        "plural_step_spaced",
        "explicit_name",
        "singular_generic",
    ]:
        reply = REPLIES[key]
        assert not unsaved_skill_claim(
            reply, _ok_save(NAME_INSURANCE)
        ), f"{key} should be silent: {reply!r}"
        assert (
            guard_skill_save_claim(reply, _ok_save(NAME_INSURANCE)) == reply
        )


def test_all_plural_affix_variants_silent():
    """Every sibling of bare plural marker must also be silent.

    Covered affixes (appear as separate tokens after ZWNJ folding):
      ها, های, هایی, هایم, هایت, هایش, هایمان, هایتان, هایشان
    """
    base_affixes = [
        "\u0647\u0627",
        "\u0647\u0627\u06cc",
        "\u0647\u0627\u06cc\u06cc",
        "\u0647\u0627\u06cc\u0645",
        "\u0647\u0627\u06cc\u062a",
        "\u0647\u0627\u06cc\u0634",
        "\u0647\u0627\u06cc\u0645\u0627\u0646",
        "\u0647\u0627\u06cc\u062a\u0627\u0646",
        "\u0647\u0627\u06cc\u0634\u0627\u0646",
    ]
    for affix in base_affixes:
        reply = f"\u0642\u062f\u0645 {affix} \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0646\u062f"  # noqa: E501
        reply_zwnj = f"\u0642\u062f\u0645\u200c{affix} \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0646\u062f"  # noqa: E501
        for variant in (reply, reply_zwnj):
            assert not unsaved_skill_claim(
                variant, _ok_save(NAME_INSURANCE)
            ), f"affix {affix!r} should be silent: {variant!r}"


def test_affixes_not_covered_documented():
    """Affixes not covered: never appear as separate token after folding.

    Not covered as separate tokens (safe via stemmer):
      ان (animate plural, attached: کاربران), ات (Arabic plural: نکات),
      ین, ون, تر, ترین

    These do not become isolated tokens via ZWNJ->space, so not trigger bug.
    """
    attached_examples = [
        "\u06a9\u0627\u0631\u0628\u0631\u0627\u0646 "
        "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0646\u062f",
        "\u0646\u06a9\u0627\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f",
    ]
    for reply in attached_examples:
        assert not unsaved_skill_claim(reply, _ok_save(NAME_INSURANCE))


def test_wrong_skill_still_warned():
    """Different procedure must still be warned, proves guard not quieter."""
    different = (
        "\u0631\u0648\u0634 \u0686\u0627\u06cc \u062f\u0645 \u06a9\u0631\u062f\u0646 "
        "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
    )
    assert unsaved_skill_claim(different, _ok_save(NAME_INSURANCE)) is True
    assert "توجه" in guard_skill_save_claim(
        different, _ok_save(NAME_INSURANCE)
    )

    same = (
        "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "
        "\u0645\u0627\u0634\u06cc\u0646 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
    )
    assert not unsaved_skill_claim(same, _ok_save(NAME_INSURANCE))


def test_fact_guard_does_not_share_defect():
    """Fact guard should not have same plural marker defect."""

    class FakeMem:
        def __init__(self, content):
            self.content = content

    reply = (
        "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a "
        "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
    )
    reply_plural = (
        "\u0648\u0627\u0642\u0639\u06cc\u062a\u200c\u0647\u0627 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."  # noqa: E501
    )

    assert unsaved_fact_claim(reply, [], []) is True
    assert unsaved_fact_claim(reply_plural, [], []) is True

    assert not unsaved_fact_claim(reply, [FakeMem("x")], [])
    assert not unsaved_fact_claim(reply_plural, [FakeMem("y")], [])
