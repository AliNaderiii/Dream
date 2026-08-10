"""M24 — readable display text and truthful Persian prompt identity.

The display reducer is deliberately tested as a pure display-layer function:
its input is the raw model reply and its output alone is inserted into the
transcript.  The logical text remains available for the store and model path.
"""

from __future__ import annotations

import inspect
import re

import desktop
from dream.agent import _BASE_PROMPT, _LANGUAGE_RULE

OWNER_MATH_REPLY = (
    "**1. پاسخ:** \\(x^2 - 5x + 6 = 0\\)\n"
    "\\[\n"
    "x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}\n"
    "\\]"
)
OWNER_MATH_DISPLAY = "1. پاسخ: x^2 - 5x + 6 = 0\nx = (-b ± √(b^2-4ac))/(2a)"
PERSIAN_SENTENCE = "پاسخ روشن و قابل خواندن است."


def test_owner_formula_reply_reduces_to_readable_plain_text():
    assert desktop.reduce_markup_for_display(OWNER_MATH_REPLY) == OWNER_MATH_DISPLAY


def test_plain_reply_is_byte_identical():
    plain = "A plain reply: 123 — بدون نشانه‌گذاری.\nSecond line."
    assert desktop.reduce_markup_for_display(plain) == plain


def test_reduction_precedes_direction_marks():
    logical, display = desktop.build_transcript_line(desktop.ASSISTANT_LABEL, OWNER_MATH_REPLY)
    assert logical == f"{desktop.ASSISTANT_LABEL}: {OWNER_MATH_REPLY}"
    assert display[0] == desktop.RLM
    assert display[-1] == desktop.RLM
    assert desktop.RLM not in display[1:-1]
    assert display[1:-1] == f"{desktop.ASSISTANT_LABEL}: {OWNER_MATH_DISPLAY}"


def test_raw_reply_stays_on_logical_store_and_model_paths():
    source = inspect.getsource(desktop.DreamDesktop._append_line)
    assert "build_transcript_line(prefix, text)" in source
    assert "reduce_markup_for_display" not in source

    controller_source = inspect.getsource(desktop.DesktopController._handle_one)
    assert "turn.reply" in controller_source
    assert "reduce_markup_for_display" not in controller_source


def test_reduction_keeps_owner_letters_digits_and_persian_words():
    reduced = desktop.reduce_markup_for_display(OWNER_MATH_REPLY)
    content = re.sub(r"\\[A-Za-z]+", "", OWNER_MATH_REPLY)
    raw_letters_digits = re.findall(r"[A-Za-z0-9\u0600-\u06ff]+", content)
    for token in raw_letters_digits:
        assert token in reduced, f"reduction lost token {token!r}: {reduced!r}"


def test_persian_sentence_still_ends_at_the_left_edge_after_reduction():
    logical, display = desktop.build_transcript_line("", PERSIAN_SENTENCE)
    assert logical == PERSIAN_SENTENCE
    assert display[0] == desktop.RLM
    assert display[-2] == "."
    assert display[-1] == desktop.RLM


def test_prompt_knows_both_names_and_uses_persian_for_persian_speakers():
    assert "Dream" in _BASE_PROMPT
    assert "رویا" in _BASE_PROMPT
    assert "فارسی" in _LANGUAGE_RULE
    assert "رویا" in _BASE_PROMPT


def test_prompt_plainly_refuses_internet_access_and_never_offers_search():
    assert "دسترسی به اینترنت نداری" in _BASE_PROMPT
    assert "پیشنهاد جستجو نده" in _BASE_PROMPT


class PromptFollowingTranscriptProbe:
    """Small deterministic stand-in: its reply is driven only by the prompt."""

    def reply(self, prompt: str, question: str) -> str:
        if "دوره" in question and "دسترسی به اینترنت نداری" not in prompt:
            return "چند سایت آموزشی می‌شناسم و می‌توانم جستجو کنم."
        if "دوره" in question:
            return "به اینترنت دسترسی ندارم و نمی‌توانم جستجو کنم."
        if "تو Dream، یعنی رویا" not in prompt:
            return "من Dream هستم."
        return "من رویا هستم."


def test_prompt_transcripts_change_for_name_and_internet_questions():
    probe = PromptFollowingTranscriptProbe()
    identity = "تو Dream، یعنی رویا، هستی؛ برای کاربر فارسی‌زبان نامت رویا است."
    internet_rule = "دسترسی به اینترنت نداری؛ این را روشن بگو و پیشنهاد جستجو نده. "
    before = _BASE_PROMPT.replace(identity, "تو Dream هستی.").replace(internet_rule, "")
    name_question = "تو کی هستی؟"
    course_question = "برای دوره‌ها لینک بده."
    before_course_reply = "چند سایت آموزشی می‌شناسم و می‌توانم جستجو کنم."
    after_course_reply = "به اینترنت دسترسی ندارم و نمی‌توانم جستجو کنم."

    assert probe.reply(before, name_question) == "من Dream هستم."
    assert probe.reply(_BASE_PROMPT, name_question) == "من رویا هستم."
    assert probe.reply(before, course_question) == before_course_reply
    assert probe.reply(_BASE_PROMPT, course_question) == after_course_reply
