"""Corruption-proof assertions against the Persian extraction prompt constant.

Ensures that the prompt sent to the extraction model contains the required
Persian and JSON fragments, four worked examples, an empty-array example, and
is free of Unicode replacement characters or stray control characters. Every
Persian string in this test module is written with backslash-u escapes so this
file cannot itself be corrupted by encoding issues.
"""

from __future__ import annotations

from dream.extraction import _EXTRACTION_PROMPT


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
