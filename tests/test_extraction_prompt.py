"""Corruption-proof assertions against the Persian extraction prompt constant.

Ensures that the prompt sent to the extraction model contains the required
Persian and JSON fragments, four worked examples, an empty-array example, and
is free of Unicode replacement characters or stray control characters. Every
Persian string in this test module is written with backslash-u escapes so this
file cannot itself be corrupted by encoding issues.
"""

from __future__ import annotations

from dream.extraction import _EXTRACTION_PROMPT, extract_facts


def test_no_unicode_replacement_character():
    assert "\uFFFD" not in _EXTRACTION_PROMPT


def test_no_stray_control_characters():
    stray = [
        c
        for c in _EXTRACTION_PROMPT
        if ord(c) < 32 and c not in ("\n", "\r", "\t")
    ]
    assert stray == []


def test_required_persian_and_json_fragments_present():
    required_json = (
        "content",
        "kind",
        "importance",
        "semantic",
        "episodic",
        "procedural",
        "[]",
    )
    for fragment in required_json:
        assert fragment in _EXTRACTION_PROMPT, f"Missing JSON fragment: {fragment}"

    # Persian terms written as \u escapes:
    # نام (name), کار (work), پروژه (project), ابزار (tool),
    # ترجیح (preference), محدودیت (constraint), تصمیم (decision)
    required_persian = (
        "\u0646\u0627\u0645",
        "\u06a9\u0627\u0631",
        "\u067e\u0631\u0648\u0698\u0647",
        "\u0627\u0628\u0632\u0627\u0631",
        "\u062a\u0631\u062c\u06cc\u062d",
        "\u0645\u062d\u062f\u0648\u062f\u06cc\u062a",
        "\u062a\u0635\u0645\u06cc\u0645",
        "\u0627\u0633\u062a\u062e\u0631\u0627\u062c",
        "\u0645\u0627\u0646\u062f\u06af\u0627\u0631",
    )
    for term in required_persian:
        assert term in _EXTRACTION_PROMPT, f"Missing Persian term: {term}"


def test_plausible_count_of_persian_characters():
    persian_chars = [c for c in _EXTRACTION_PROMPT if 0x0600 <= ord(c) <= 0x06FF]
    assert len(persian_chars) >= 200


def test_four_worked_examples_present():
    # "کاربر:" and "خروجی:"
    user_label = "\u06a9\u0627\u0631\u0628\u0631:"
    output_label = "\u062e\u0631\u0648\u062c\u06cc:"
    assert _EXTRACTION_PROMPT.count(user_label) >= 4
    assert _EXTRACTION_PROMPT.count(output_label) >= 4


def test_empty_array_example_intact():
    output_label = "\u062e\u0631\u0648\u062c\u06cc:"
    assert output_label in _EXTRACTION_PROMPT
    first_output_index = _EXTRACTION_PROMPT.find(output_label) + len(output_label)
    snippet = _EXTRACTION_PROMPT[first_output_index:].strip()
    assert snippet.startswith("[]")


def test_prompt_has_a_worked_example_with_a_family_name():
    full_name = "\u0639\u0644\u06cc\u0631\u0636\u0627 \u0646\u0627\u062f\u0631\u06cc"
    full_name_fact = (
        "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc\u0631\u0636\u0627 "
        "\u0646\u0627\u062f\u0631\u06cc \u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
    )
    assert full_name in _EXTRACTION_PROMPT
    assert full_name_fact in _EXTRACTION_PROMPT


def test_prompt_tells_extractor_to_preserve_exact_name_wording():
    instruction = (
        "\u0646\u0627\u0645 \u0627\u0641\u0631\u0627\u062f \u0631\u0627 \u0628\u0627 "
        "\u0647\u0645\u0627\u0646 \u0648\u0627\u0698\u0647\u200c\u0647\u0627\u06cc "
        "\u06a9\u0627\u0631\u0628\u0631 \u062d\u0641\u0638 \u06a9\u0646 \u0648 "
        "\u0646\u0627\u0645 \u062e\u0627\u0646\u0648\u0627\u062f\u06af\u06cc \u0631\u0627 "
        "\u062d\u0630\u0641 \u0646\u06a9\u0646."
    )
    assert instruction in _EXTRACTION_PROMPT


class _PromptSensitiveFullNameBackend:
    def chat(self, messages):
        prompt = str(messages[0]["content"])
        family_name = "\u0646\u0627\u062f\u0631\u06cc"
        full_name = "\u0639\u0644\u06cc\u0631\u0636\u0627 \u0646\u0627\u062f\u0631\u06cc"
        if family_name in prompt and full_name in prompt:
            content = (
                "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc\u0631\u0636\u0627 "
                "\u0646\u0627\u062f\u0631\u06cc \u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
            )
        else:
            content = (
                "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc\u0631\u0636\u0627 "
                "\u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
            )
        return {
            "content": (
                '[{"content": "'
                + content
                + '", "kind": "semantic", "importance": 0.9}]'
            )
        }


def test_scripted_full_name_extraction_keeps_the_family_name():
    sentence = (
        "\u0627\u0633\u0645 \u06a9\u0627\u0645\u0644 \u0645\u0646 "
        "\u0639\u0644\u06cc\u0631\u0636\u0627 \u0646\u0627\u062f\u0631\u06cc \u0627\u0633\u062a."
    )
    result = extract_facts(_PromptSensitiveFullNameBackend(), sentence)
    contents = [fact.content for fact in result.facts]
    assert any("\u0646\u0627\u062f\u0631\u06cc" in content for content in contents), contents
