"""Pin the natural Persian date parser (M3).

The owner had to type dates as digits while real people write «فردا»,
«پانزدهم مهر», «اول هر ماه». These tests pin the parser that turns such
phrases into the same midnight timestamps the scheduler already uses,
the Jalali module staying the single source of calendar truth, and the
CLI wiring that lets /remind accept them. The acceptance table below is
the milestone's required table: every phrase with its resolved date,
run against a fixed reference instant (1405-05-17 noon) so the results
are deterministic and repeatable.

Every new Persian string in this module is a backslash-u escape,
matching tests/test_extraction_prompt.py, so it cannot be corrupted in
transit.
"""

from __future__ import annotations

import pytest

import cli
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore
from dream.reminders import (
    format_jalali,
    parse_date_to_timestamp,
    parse_persian_date,
)

# Fixed reference instant: noon on 1405-05-17 (a Saturday in the Gregorian)
# calendar), so weekday and next-occurrence phrases resolve deterministically.
_NOW = parse_date_to_timestamp("1405-05-17") + 12 * 3600


_TABLE: tuple[tuple[str, str], ...] = (
    (
        "\u0627\u0645\u0631\u0648\u0632",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0031\u0037",  # امروز
    ),
    (
        "\u0641\u0631\u062f\u0627",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0031\u0038",  # فردا
    ),
    (
        "\u067e\u0633\u200c\u0641\u0631\u062f\u0627",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0031\u0039",  # پس‌فردا
    ),
    (
        "\u062f\u06cc\u0631\u0648\u0632",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0031\u0036",  # دیروز
    ),
    (
        "\u067e\u0631\u06cc\u0631\u0648\u0632",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0031\u0035",  # پریروز
    ),
    (
        "\u0647\u0641\u062a\u0647 \u0628\u0639\u062f",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0032\u0034",  # هفته بعد
    ),
    (
        "\u0647\u0641\u062a\u0647"
        " \u0622\u06cc\u0646\u062f\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0032\u0034",  # هفته آینده
    ),
    (
        "\u0645\u0627\u0647 \u0628\u0639\u062f",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0036\u002d\u0031\u0037",  # ماه بعد
    ),
    (
        "\u0633\u0627\u0644 \u0628\u0639\u062f",
        "\u0031\u0034\u0030\u0036\u002d\u0030\u0035\u002d\u0031\u0037",  # سال بعد
    ),
    (
        "\u0633\u0647 \u0631\u0648\u0632"
        " \u0628\u0639\u062f",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0032\u0030",  # سه روز بعد
    ),
    (
        "\u062f\u0648 \u0647\u0641\u062a\u0647"
        " \u0628\u0639\u062f",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0033\u0031",  # دو هفته بعد
    ),
    (
        "\u06f1\u06f5 \u0631\u0648\u0632"
        " \u0628\u0639\u062f",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0036\u002d\u0030\u0031",  # ۱۵ روز بعد
    ),
    (
        "\u062f\u0648 \u0645\u0627\u0647"
        " \u0628\u0639\u062f",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0031\u0037",  # دو ماه بعد
    ),
    (
        "\u067e\u0627\u0646\u0632\u062f\u0647\u0645"
        " \u0645\u0647\u0631",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0031\u0035",  # پانزدهم مهر
    ),
    (
        "\u06f1\u06f5 \u0645\u0647\u0631",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0031\u0035",  # ۱۵ مهر
    ),
    (
        "\u06f1\u06f5\u0627\u0645 \u0645\u0647\u0631",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0031\u0035",  # ۱۵ام مهر
    ),
    (
        "\u06f1\u06f5 \u0645\u0647\u0631"
        " \u06f1\u06f4\u06f0\u06f4",
        "\u0031\u0034\u0030\u0034\u002d\u0030\u0037\u002d\u0031\u0035",  # ۱۵ مهر ۱۴۰۴
    ),
    (
        "\u0627\u0648\u0644 \u0647\u0631"
        " \u0645\u0627\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0036\u002d\u0030\u0031",  # اول هر ماه
    ),
    (
        "\u067e\u0627\u0646\u0632\u062f\u0647\u0645"
        " \u0647\u0631 \u0645\u0627\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0036\u002d\u0031\u0035",  # پانزدهم هر ماه
    ),
    (
        "\u0633\u06cc\u200c\u0627\u0645"
        " \u0627\u0633\u0641\u0646\u062f",
        "\u0031\u0034\u0030\u0038\u002d\u0031\u0032\u002d\u0033\u0030",  # سی‌ام اسفند
    ),
    (
        "\u0628\u06cc\u0633\u062a \u0648"
        " \u0646\u0647\u0645"
        " \u0627\u0633\u0641\u0646\u062f",
        "\u0031\u0034\u0030\u0035\u002d\u0031\u0032\u002d\u0032\u0039",  # بیست و نهم اسفند
    ),
    (
        "\u0634\u0646\u0628\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0032\u0034",  # شنبه
    ),
    (
        "\u06cc\u06a9\u0634\u0646\u0628\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0031\u0038",  # یکشنبه
    ),
    (
        "\u062c\u0645\u0639\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0032\u0033",  # جمعه
    ),
    (
        "\u0634\u0646\u0628\u0647"
        " \u0647\u0641\u062a\u0647"
        " \u0622\u06cc\u0646\u062f\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0033\u0031",  # شنبه هفته آینده
    ),
    (
        "\u0622\u062e\u0631 \u0645\u0627\u0647",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0035\u002d\u0033\u0031",  # آخر ماه
    ),
    (
        "\u062f\u0647 \u0645\u0647\u0631",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0031\u0030",  # ده مهر
    ),
    (
        "\u062f\u0647\u0645 \u0645\u0647\u0631",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0031\u0030",  # دهم مهر
    ),
    (
        "\u0628\u06cc\u0633\u062a\u0645"
        " \u0628\u0647\u0645\u0646"
        " \u06f1\u06f4\u06f0\u06f5",
        "\u0031\u0034\u0030\u0035\u002d\u0031\u0031\u002d\u0032\u0030",  # بیستم بهمن ۱۴۰۵
    ),
    (
        "\u0627\u0648\u0644"
        " \u0641\u0631\u0648\u0631\u062f\u06cc\u0646",
        "\u0031\u0034\u0030\u0036\u002d\u0030\u0031\u002d\u0030\u0031",  # اول فروردین
    ),
    (
        "\u067e\u0627\u0646\u0632\u062f\u0647\u0645"
        " \u0622\u0628\u0627\u0646",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0038\u002d\u0031\u0035",  # پانزدهم آبان
    ),
    (
        "\u0633\u06cc\u200c\u0627\u0645"
        " \u0634\u0647\u0631\u06cc\u0648\u0631",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0036\u002d\u0033\u0030",  # سی‌ام شهریور
    ),
    (
        "\u06cc\u06a9\u0645 \u0645\u0647\u0631",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0030\u0031",  # یکم مهر
    ),
    (
        "\u0633\u06cc\u200c\u0627\u0645"
        " \u062a\u06cc\u0631",
        "\u0031\u0034\u0030\u0036\u002d\u0030\u0034\u002d\u0033\u0030",  # سی‌ام تیر
    ),
)


@pytest.mark.parametrize(("phrase", "expected"), _TABLE)
def test_phrase_table_resolves_the_expected_date(phrase, expected):
    """Each real phrase resolves to its pinned Jalali date."""
    resolved = parse_persian_date(phrase, now=_NOW)
    assert format_jalali(resolved) == expected


# Spelling variants that must all agree: Arabic yeh vs Farsi yeh, ZWNJ vs
# space, joined vs spaced compounds, Persian vs ASCII digits.
_VARIANTS: tuple[tuple[str, str], ...] = (
    (
        "\u0628\u064a\u0633\u062a \u0648"
        " \u064a\u0643\u0645 \u0645\u0647\u0631",
        "\u0628\u06cc\u0633\u062a \u0648"
        " \u06cc\u06a9\u0645 \u0645\u0647\u0631",  # بيست و يكم مهر / بیست و یکم مهر
    ),
    (
        "\u067e\u0633\u200c\u0641\u0631\u062f\u0627",
        "\u067e\u0633 \u0641\u0631\u062f\u0627",  # پس‌فردا / پس فردا
    ),
    (
        "\u067e\u0633\u200c\u0641\u0631\u062f\u0627",
        "\u067e\u0633\u200c\u0641\u0631\u062f\u0627",  # پس‌فردا / پس‌فردا
    ),
    (
        "\u0633\u06cc\u200c\u0627\u0645"
        " \u0645\u0647\u0631",
        "\u06f3\u06f0\u0627\u0645 \u0645\u0647\u0631",  # سی‌ام مهر / ۳۰ام مهر
    ),
    (
        "\u0628\u06cc\u0633\u062a\u200c\u0648\u06cc\u06a9\u0645"
        " \u0645\u0647\u0631",
        "\u0628\u06cc\u0633\u062a \u0648"
        " \u06cc\u06a9\u0645 \u0645\u0647\u0631",  # بیست‌ویکم مهر / بیست و یکم مهر
    ),
    (
        "\u064a\u0643\u0634\u0646\u0628\u0647",
        "\u06cc\u06a9\u0634\u0646\u0628\u0647",  # يكشنبه / یکشنبه
    ),
    (
        "\u067e\u0627\u0646\u0632\u062f\u0647\u0645"
        " \u0622\u0630\u0631",
        "\u067e\u0627\u0646\u0632\u062f\u0647\u0645"
        " \u0627\u0630\u0631",  # پانزدهم آذر / پانزدهم اذر
    ),
)


@pytest.mark.parametrize(("variant", "canonical"), _VARIANTS)
def test_spelling_variants_agree(variant, canonical):
    left = parse_persian_date(variant, now=_NOW)
    right = parse_persian_date(canonical, now=_NOW)
    assert left == right


_AMBIGUOUS: tuple[str, ...] = (
    "\u0645\u0647\u0631",  # مهر
    "\u0628\u06cc\u0633\u062a\u0645",  # بیستم
    "\u0633\u0647",  # سه
)


@pytest.mark.parametrize("phrase", _AMBIGUOUS)
def test_ambiguous_phrase_is_rejected_with_an_example(phrase):
    """A month without a day or a day without a month is never guessed."""
    with pytest.raises(ValueError) as excinfo:
        parse_persian_date(phrase, now=_NOW)
    assert "ambiguous" in str(excinfo.value)
    assert "try" in str(excinfo.value)


_REJECTED: tuple[tuple[str, str], ...] = (
    (
        "\u0633\u06cc \u0648 \u06cc\u06a9\u0645"
        " \u0622\u0628\u0627\u0646",
        "\u006e\u006f \u0076\u0061\u006c\u0069\u0064"
        " \u0064\u0061\u0074\u0065",  # سی و یکم آبان
    ),
    (
        "\u06f1\u06f5 \u0645\u0647\u0631"
        " \u0032\u0030\u0032\u0036",
        "\u0047\u0072\u0065\u0067\u006f\u0072\u0069\u0061\u006e",  # ۱۵ مهر 2026
    ),
    (
        "\u06a9\u062a\u0627\u0628"
        " \u0628\u062e\u0648\u0627\u0646",
        "\u0074\u0072\u0079",  # کتاب بخوان
    ),
)


@pytest.mark.parametrize(("phrase", "hint"), _REJECTED)
def test_impossible_or_unknown_phrase_is_rejected_with_a_hint(phrase, hint):
    with pytest.raises(ValueError) as excinfo:
        parse_persian_date(phrase, now=_NOW)
    assert hint in str(excinfo.value)


# ---------------------------------------------------------------------------
# The /remind command accepts natural Persian dates
# ---------------------------------------------------------------------------


_CLI_CASES: tuple[tuple[str, str, str, int | None, int | None], ...] = (
    (
        "\u002f\u0072\u0065\u006d\u0069\u006e\u0064"
        " \u067e\u0627\u0646\u0632\u062f\u0647\u0645"
        " \u0645\u0647\u0631 \u06f1\u06f4\u06f0\u06f5"
        " \u067e\u0631\u062f\u0627\u062e\u062a"
        " \u0642\u0633\u0637",
        "\u0031\u0034\u0030\u0035\u002d\u0030\u0037\u002d\u0031\u0035",
        "\u067e\u0631\u062f\u0627\u062e\u062a"
        " \u0642\u0633\u0637",
        None,
        None,  # /remind پانزدهم مهر ۱۴۰۵ پرداخت قسط
    ),
    (
        "\u002f\u0072\u0065\u006d\u0069\u006e\u0064"
        " \u06f1\u06f5\u0627\u0645 \u0645\u0647\u0631"
        " \u06f1\u06f4\u06f0\u06f4"
        " \u0628\u06cc\u0645\u0647"
        " \u0645\u0627\u0634\u06cc\u0646 \u0647\u0631"
        " \u0633\u0627\u0644",
        "\u0031\u0034\u0030\u0034\u002d\u0030\u0037\u002d\u0031\u0035",
        "\u0628\u06cc\u0645\u0647"
        " \u0645\u0627\u0634\u06cc\u0646",
        None,
        12,  # /remind ۱۵ام مهر ۱۴۰۴ بیمه ماشین هر سال
    ),
    (
        "\u002f\u0072\u0065\u006d\u0069\u006e\u0064"
        " \u0628\u06cc\u0633\u062a \u0648"
        " \u0646\u0647\u0645"
        " \u0627\u0633\u0641\u0646\u062f"
        " \u06f1\u06f4\u06f0\u06f4"
        " \u0635\u0648\u0631\u062a\u062d\u0633\u0627\u0628",
        "\u0031\u0034\u0030\u0034\u002d\u0031\u0032\u002d\u0032\u0039",
        "\u0635\u0648\u0631\u062a\u062d\u0633\u0627\u0628",
        None,
        None,  # /remind بیست و نهم اسفند ۱۴۰۴ صورتحساب
    ),
)


@pytest.mark.parametrize(("command", "due", "text", "days", "months"), _CLI_CASES)
def test_remind_command_accepts_natural_dates(command, due, text, days, months):
    """The CLI date slot accepts a Persian phrase; the rest is text/repeat."""
    store = MemoryStore(":memory:")
    dream = Dream(store, EchoBackend())
    output: list[str] = []
    assert cli.dispatch_command(command, dream, output.append) is True
    assert due in output[0]
    reminders = store.list_reminders()
    assert len(reminders) == 1
    assert reminders[0].text == text
    assert reminders[0].repeat_days == days
    assert reminders[0].repeat_months == months


def test_remind_command_rejects_ambiguous_date_with_example():
    """«مهر» alone names a month, not a date: rejected with a worked example."""
    store = MemoryStore(":memory:")
    dream = Dream(store, EchoBackend())
    output: list[str] = []
    cli.dispatch_command("/remind مهر قسط", dream, output.append)
    assert "ambiguous" in output[0]
    assert "15" in output[0]
    assert len(store.list_reminders()) == 0


def test_remind_command_usage_still_mentions_unparseable():
    """A non-date argument keeps the pinned «Unparseable» guidance."""
    store = MemoryStore(":memory:")
    dream = Dream(store, EchoBackend())
    output: list[str] = []
    cli.dispatch_command("/remind not-a-date text", dream, output.append)
    assert "unparseable" in output[0].lower()
    assert len(store.list_reminders()) == 0
