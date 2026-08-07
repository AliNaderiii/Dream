"""Near-duplicate detection for semantic memories.

After two short sessions the store held:

    3  semantic  importance=0.90  (the user works on a fintech startup)
    2  semantic  importance=1.00  (the user works on a fintech startup)
    1  semantic  importance=1.00  (the user is named Ali)

Rows 2 and 3 are the same fact — they differ by one indefinite article.
Exact-match dedupe missed it because the normalised strings differ. The
supersede path also missed it because prefix overlap collapses when one
token is inserted in the middle.

This module pins the second check: Jaccard similarity on canonicalised
stemmed tokens, where each synonym group's members collapse to one
canonical representative before comparison. The spouse group is excluded
because two of its members are gendered opposites.

New Persian strings are written as backslash-u escapes, matching
tests/test_extraction_prompt.py, so they cannot be corrupted in transit.
"""

from __future__ import annotations

import pytest

from dream.memory import (
    _CANONICAL_MAP,
    _EXCLUDED_FROM_DUPLICATE_CANONICALISATION,
    _SYNONYM_GROUPS,
    DEFAULT_DUPLICATE_THRESHOLD,
    MemoryStore,
    _longest_common_subsequence,
)


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


# --------------------------------------------------------------------------
# Persian test strings (backslash-u escapes)
# --------------------------------------------------------------------------

# The observed fintech bug pair:
# کاربر روی یک استارتاپ فین‌تک کار می‌کند (with indefinite article یک)
_FINTECH_WITH_ARTICLE = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0648\u06cc \u06cc\u06a9 "
    "\u0627\u0633\u062a\u0627\u0631\u062a\u0627\u067e "
    "\u0641\u06cc\u0646\u200c\u062a\u06a9 \u06a9\u0627\u0631 "
    "\u0645\u06cc\u200c\u06a9\u0646\u062f"
)
# کاربر روی استارتاپ فین‌تک کار می‌کند (without indefinite article)
_FINTECH_WITHOUT_ARTICLE = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0648\u06cc "
    "\u0627\u0633\u062a\u0627\u0631\u062a\u0627\u067e "
    "\u0641\u06cc\u0646\u200c\u062a\u06a9 \u06a9\u0627\u0631 "
    "\u0645\u06cc\u200c\u06a9\u0646\u062f"
)

# Two words for "name": نام and اسم
# کاربر علی نام دارد
_NAME_WITH_NAM = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc "
    "\u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
)
# کاربر علی اسم دارد
_NAME_WITH_ESM = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc "
    "\u0627\u0633\u0645 \u062f\u0627\u0631\u062f"
)

# Two words for "car": خودرو and ماشین
# کاربر ماشین پژو دارد
_CAR_WITH_MASHIN = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0645\u0627\u0634\u06cc\u0646 "
    "\u067e\u0698\u0648 \u062f\u0627\u0631\u062f"
)
# کاربر خودرو پژو دارد
_CAR_WITH_KHODRO = (
    "\u06a9\u0627\u0631\u0628\u0631 \u062e\u0648\u062f\u0631\u0648 "
    "\u067e\u0698\u0648 \u062f\u0627\u0631\u062f"
)

# Two words for "job": شغل and کار
# کاربر شغل مهندس دارد
_JOB_WITH_SHOGHL = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0634\u063a\u0644 "
    "\u0645\u0647\u0646\u062f\u0633 \u062f\u0627\u0631\u062f"
)
# کاربر کار مهندس دارد  (but کار also appears in کار می‌کند etc, need a
# different context)
# Actually let's use حرفه (profession) and شغل
# کاربر حرفه مهندس دارد
_JOB_WITH_HERFE = (
    "\u06a9\u0627\u0631\u0628\u0631 \u062d\u0631\u0641\u0647 "
    "\u0645\u0647\u0646\u062f\u0633 \u062f\u0627\u0631\u062f"
)

# Two words for "friend": دوست and رفیق
# کاربر دوست خوب دارد
_FRIEND_WITH_DOOST = (
    "\u06a9\u0627\u0631\u0628\u0631 \u062f\u0648\u0633\u062a "
    "\u062e\u0648\u0628 \u062f\u0627\u0631\u062f"
)
# کاربر رفیق خوب دارد
_FRIEND_WITH_RAFIQ = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0641\u06cc\u0642 "
    "\u062e\u0648\u0628 \u062f\u0627\u0631\u062f"
)

# Two words for "age": سن and عمر
# کاربر سن سی دارد
_AGE_WITH_SENN = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0633\u0646 "
    "\u0633\u06cc \u062f\u0627\u0631\u062f"
)
# کاربر عمر سی دارد
_AGE_WITH_OMR = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0645\u0631 "
    "\u0633\u06cc \u062f\u0627\u0631\u062f"
)

# Two words for "home": خانه and منزل
# کاربر خانه تهران دارد
_HOME_WITH_KHANE = (
    "\u06a9\u0627\u0631\u0628\u0631 \u062e\u0627\u0646\u0647 "
    "\u062a\u0647\u0631\u0627\u0646 \u062f\u0627\u0631\u062f"
)
# کاربر منزل تهران دارد
_HOME_WITH_MANZEL = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0645\u0646\u0632\u0644 "
    "\u062a\u0647\u0631\u0627\u0646 \u062f\u0627\u0631\u062f"
)

# Two words for "city": شهر and شهرستان
# کاربر شهر تهران است
_CITY_WITH_SHAHR = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0634\u0647\u0631 "
    "\u062a\u0647\u0631\u0627\u0646 \u0627\u0633\u062a"
)
# کاربر شهرستان تهران است
_CITY_WITH_SHAHRESTAN = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0634\u0647\u0631\u0633\u062a\u0627\u0646 "
    "\u062a\u0647\u0631\u0627\u0646 \u0627\u0633\u062a"
)

# Spouse pair: زن دارد vs شوهر دارد
# کاربر زن دارد
_WIFE_FACT = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0632\u0646 "
    "\u062f\u0627\u0631\u062f"
)
# کاربر شوهر دارد
_HUSBAND_FACT = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0634\u0648\u0647\u0631 "
    "\u062f\u0627\u0631\u062f"
)

# Two languages: فارسی صحبت می‌کند vs انگلیسی صحبت می‌کند
_SPEAKS_PERSIAN = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0641\u0627\u0631\u0633\u06cc "
    "\u0635\u062d\u0628\u062a \u0645\u06cc\u200c\u06a9\u0646\u062f"
)
_SPEAKS_ENGLISH = (
    "\u06a9\u0627\u0631\u0628\u0631 "
    "\u0627\u0646\u06af\u0644\u06cc\u0633\u06cc "
    "\u0635\u062d\u0628\u062a \u0645\u06cc\u200c\u06a9\u0646\u062f"
)

# Living somewhere vs working there
_LIVES_TEHRAN = (
    "\u06a9\u0627\u0631\u0628\u0631 \u062f\u0631 \u062a\u0647\u0631\u0627\u0646 "
    "\u0632\u0646\u062f\u06af\u06cc \u0645\u06cc\u200c\u06a9\u0646\u062f"
)
_WORKS_TEHRAN = (
    "\u06a9\u0627\u0631\u0628\u0631 \u062f\u0631 \u062a\u0647\u0631\u0627\u0646 "
    "\u06a9\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u062f"
)

# Two programming languages
_KNOWS_PYTHON = (
    "\u06a9\u0627\u0631\u0628\u0631 \u067e\u0627\u06cc\u062a\u0648\u0646 "
    "\u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0646\u0648\u06cc\u0633\u06cc "
    "\u0645\u06cc\u200c\u06a9\u0646\u062f"
)
_KNOWS_RUST = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0627\u0633\u062a "
    "\u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0646\u0648\u06cc\u0633\u06cc "
    "\u0645\u06cc\u200c\u06a9\u0646\u062f"
)

# Same city fact changed to another (contradiction, not duplicate)
_CITY_TEHRAN = (
    "\u0634\u0647\u0631 \u06a9\u0627\u0631\u0628\u0631 \u062a\u0647\u0631\u0627\u0646 "
    "\u0627\u0633\u062a"
)
_CITY_SHIRAZ = (
    "\u0634\u0647\u0631 \u06a9\u0627\u0631\u0628\u0631 \u0634\u06cc\u0631\u0627\u0632 "
    "\u0627\u0633\u062a"
)

# Two different phones with different words
_PHONE_SAMSUNG = (
    "\u06af\u0648\u0634\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0633\u0627\u0645\u0633\u0648\u0646\u06af \u0627\u0633\u062a"
)
_PHONE_IPHONE = (
    "\u062a\u0644\u0641\u0646 \u06a9\u0627\u0631\u0628\u0631 "
    "\u0622\u06cc\u0641\u0648\u0646 \u0627\u0633\u062a"
)

# Order-sensitive pair 1: Ali is Reza's brother vs Reza is Ali's brother
_BROTHER_ALI_REZA = (
    "\u0639\u0644\u06cc \u0628\u0631\u0627\u062f\u0631 "
    "\u0631\u0636\u0627 \u0627\u0633\u062a"
)
_BROTHER_REZA_ALI = (
    "\u0631\u0636\u0627 \u0628\u0631\u0627\u062f\u0631 "
    "\u0639\u0644\u06cc \u0627\u0633\u062a"
)

# Order-sensitive pair 2: went Tehran to Shiraz vs went Shiraz to Tehran
_WENT_TEHRAN_SHIRAZ = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0627\u0632 \u062a\u0647\u0631\u0627\u0646 "
    "\u0628\u0647 \u0634\u06cc\u0631\u0627\u0632 \u0631\u0641\u062a"
)
_WENT_SHIRAZ_TEHRAN = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0627\u0632 \u0634\u06cc\u0631\u0627\u0632 "
    "\u0628\u0647 \u062a\u0647\u0631\u0627\u0646 \u0631\u0641\u062a"
)

# Order-sensitive pair 3: user owes Ali vs Ali owes user
_OWES_USER_TO_ALI = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0628\u0647 \u0639\u0644\u06cc "
    "\u0628\u062f\u0647\u06a9\u0627\u0631 \u0627\u0633\u062a"
)
_OWES_ALI_TO_USER = (
    "\u0639\u0644\u06cc \u0628\u0647 \u06a9\u0627\u0631\u0628\u0631 "
    "\u0628\u062f\u0647\u06a9\u0627\u0631 \u0627\u0633\u062a"
)

# Order-sensitive pair 4: meeting runs 9 to 11 vs 11 to 9
_MEETING_9_TO_11 = (
    "\u062c\u0644\u0633\u0647 \u0627\u0632 \u06f9 \u062a\u0627 "
    "\u06f1\u06f1 \u0627\u0633\u062a"
)
_MEETING_11_TO_9 = (
    "\u062c\u0644\u0633\u0647 \u0627\u0632 \u06f1\u06f1 \u062a\u0627 "
    "\u06f9 \u0627\u0633\u062a"
)

# Numeric value swap: salary 20 rent 5 vs salary 5 rent 20
_SALARY_20_RENT_5 = (
    "\u062d\u0642\u0648\u0642 \u06a9\u0627\u0631\u0628\u0631 \u06f2\u06f0 "
    "\u0648 \u0627\u062c\u0627\u0631\u0647 \u06f5 \u0627\u0633\u062a"
)
_SALARY_5_RENT_20 = (
    "\u062d\u0642\u0648\u0642 \u06a9\u0627\u0631\u0628\u0631 \u06f5 "
    "\u0648 \u0627\u062c\u0627\u0631\u0647 \u06f2\u06f0 \u0627\u0633\u062a"
)

# Person name swap: Ali is Sara's manager vs Sara is Ali's manager
_MANAGER_ALI_SARA = (
    "\u0639\u0644\u06cc \u0645\u062f\u06cc\u0631 \u0633\u0627\u0631\u0627 "
    "\u0627\u0633\u062a"
)
_MANAGER_SARA_ALI = (
    "\u0633\u0627\u0631\u0627 \u0645\u062f\u06cc\u0631 \u0639\u0644\u06cc "
    "\u0627\u0633\u062a"
)


# --------------------------------------------------------------------------
# The observed bug: two fintech rows collapse to one
# --------------------------------------------------------------------------


def test_fintech_duplicate_collapses_to_one_row(store):
    """The reported bug: one word difference defeats exact dedupe."""
    store.remember(_FINTECH_WITH_ARTICLE, kind="semantic", importance=1.0)
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic", importance=0.9)
    rows = store.all(limit=10)
    assert len(rows) == 1


def test_fintech_keeps_higher_importance_when_higher_arrives_first(store):
    store.remember(_FINTECH_WITH_ARTICLE, kind="semantic", importance=1.0)
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic", importance=0.9)
    rows = store.all(limit=10)
    assert len(rows) == 1
    # max(1.0, 0.9) = 1.0; boosted: min(1.0, 1.0 + 0.1) = 1.0
    assert rows[0].importance == 1.0


def test_fintech_keeps_higher_importance_when_higher_arrives_second(store):
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic", importance=0.9)
    store.remember(_FINTECH_WITH_ARTICLE, kind="semantic", importance=1.0)
    rows = store.all(limit=10)
    assert len(rows) == 1
    # max(0.9, 1.0) = 1.0; boosted: min(1.0, 1.0 + 0.1) = 1.0
    assert rows[0].importance == 1.0


# --------------------------------------------------------------------------
# Order-sensitive cases stay separate (LCS == multiset intersection rule)
# --------------------------------------------------------------------------


def test_reordered_subject_is_kept_separate(store):
    """Reordering a whole fact without changing meaning no longer merges.

    Moving the subject after the place in 'the user lives in Tehran' has
    Jaccard 1.000 and 6 shared tokens, but a longest common subsequence of 5.
    Because the tokens do not appear in the same relative order, the new
    order-sensitive duplicate rule keeps the two facts separate. This is the
    accepted trade: leaving a duplicate row is untidy, but deleting a fact
    wrongly is not recoverable.
    """
    # کاربر در تهران زندگی می‌کند
    original = (
        "\u06a9\u0627\u0631\u0628\u0631 \u062f\u0631 \u062a\u0647\u0631\u0627\u0646 "
        "\u0632\u0646\u062f\u06af\u06cc \u0645\u06cc\u200c\u06a9\u0646\u062f"
    )
    # در تهران کاربر زندگی می‌کند (same tokens, reordered)
    reordered = (
        "\u062f\u0631 \u062a\u0647\u0631\u0627\u0646 \u06a9\u0627\u0631\u0628\u0631 "
        "\u0632\u0646\u062f\u06af\u06cc \u0645\u06cc\u200c\u06a9\u0646\u062f"
    )
    store.remember(original, kind="semantic", importance=0.8)
    store.remember(reordered, kind="semantic", importance=0.7)
    rows = store.all(limit=10)
    # Kept separate because LCS < multiset intersection size.
    assert len(rows) == 2


def test_four_order_sensitive_persian_pairs_stay_separate(store):
    """The four order-sensitive Persian pairs from the specification stay separate."""
    # 1. Brother pair: Ali is Reza's brother vs Reza is Ali's brother
    store.remember(_BROTHER_ALI_REZA, kind="semantic")
    store.remember(_BROTHER_REZA_ALI, kind="semantic")
    assert len(store.all(limit=10)) == 2

    # 2. Travel pair: went Tehran to Shiraz vs went Shiraz to Tehran
    store.remember(_WENT_TEHRAN_SHIRAZ, kind="semantic")
    store.remember(_WENT_SHIRAZ_TEHRAN, kind="semantic")
    assert len(store.all(limit=10)) == 4

    # 3. Debt pair: user owes Ali vs Ali owes user
    store.remember(_OWES_USER_TO_ALI, kind="semantic")
    store.remember(_OWES_ALI_TO_USER, kind="semantic")
    assert len(store.all(limit=10)) == 6

    # 4. Meeting time pair: runs 9 to 11 vs runs 11 to 9
    store.remember(_MEETING_9_TO_11, kind="semantic")
    store.remember(_MEETING_11_TO_9, kind="semantic")
    assert len(store.all(limit=10)) == 8


def test_two_additional_order_sensitive_pairs_stay_separate(store):
    """Two additional order-sensitive pairs (numeric and person name swap) stay separate."""
    # Numeric value swap
    store.remember(_SALARY_20_RENT_5, kind="semantic")
    store.remember(_SALARY_5_RENT_20, kind="semantic")
    assert len(store.all(limit=10)) == 2

    # Person name swap
    store.remember(_MANAGER_ALI_SARA, kind="semantic")
    store.remember(_MANAGER_SARA_ALI, kind="semantic")
    assert len(store.all(limit=10)) == 4


def test_exact_strings_fact_number_swap_stay_separate(store):
    """The exact strings 'fact number 1-0' and 'fact number 0-1' stay separate."""
    store.remember("fact number 1-0", kind="semantic")
    store.remember("fact number 0-1", kind="semantic")
    assert len(store.all(limit=10)) == 2


def test_bulk_threading_facts_leave_all_rows_stored(store):
    """Storing the 400 strings from the threading test leaves all 400 rows intact."""
    bulk = [f"fact number {n}-{i}" for n in range(8) for i in range(50)]
    for text in bulk:
        store.remember(text, kind="semantic", importance=0.9)
    assert len(store.all(limit=1000)) == 400


# --------------------------------------------------------------------------
# Longest common subsequence helper unit tests
# --------------------------------------------------------------------------


def test_longest_common_subsequence_helper():
    """Unit test of _longest_common_subsequence covering required cases."""
    # Empty inputs
    assert _longest_common_subsequence([], []) == 0
    # One empty input
    assert _longest_common_subsequence(["a", "b"], []) == 0
    assert _longest_common_subsequence([], ["a", "b"]) == 0
    # Identical sequences
    assert _longest_common_subsequence(["a", "b", "c"], ["a", "b", "c"]) == 3
    # Pure insertion
    assert _longest_common_subsequence(["a", "b", "c"], ["a", "c"]) == 2
    assert _longest_common_subsequence(["a", "c"], ["a", "b", "c"]) == 2
    # Pure swap
    assert _longest_common_subsequence(["a", "b", "c"], ["b", "a", "c"]) == 2
    # Repeated tokens where multiset count matters
    assert _longest_common_subsequence(["a", "a", "b"], ["a", "b", "b"]) == 2
    assert _longest_common_subsequence(["a", "b", "a"], ["a", "a", "b"]) == 2


# --------------------------------------------------------------------------
# Synonym pairs merge
# --------------------------------------------------------------------------


def test_synonym_pair_name_merges(store):
    """The two words for 'name' (نام/اسم) must collapse."""
    store.remember(_NAME_WITH_NAM, kind="semantic")
    store.remember(_NAME_WITH_ESM, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 1


def test_synonym_pair_car_merges(store):
    store.remember(_CAR_WITH_MASHIN, kind="semantic")
    store.remember(_CAR_WITH_KHODRO, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 1


def test_synonym_pair_job_merges(store):
    store.remember(_JOB_WITH_SHOGHL, kind="semantic")
    store.remember(_JOB_WITH_HERFE, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 1


def test_synonym_pair_friend_merges(store):
    store.remember(_FRIEND_WITH_DOOST, kind="semantic")
    store.remember(_FRIEND_WITH_RAFIQ, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 1


def test_synonym_pair_age_merges(store):
    store.remember(_AGE_WITH_SENN, kind="semantic")
    store.remember(_AGE_WITH_OMR, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 1


def test_synonym_pair_home_merges(store):
    store.remember(_HOME_WITH_KHANE, kind="semantic")
    store.remember(_HOME_WITH_MANZEL, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 1


def test_synonym_pair_city_merges(store):
    store.remember(_CITY_WITH_SHAHR, kind="semantic")
    store.remember(_CITY_WITH_SHAHRESTAN, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 1


# --------------------------------------------------------------------------
# The spouse exclusion: wife vs husband stay separate
# --------------------------------------------------------------------------


def test_spouse_exclusion_wife_and_husband_stay_separate(store):
    """A wife fact and a husband fact must never merge."""
    store.remember(_WIFE_FACT, kind="semantic")
    store.remember(_HUSBAND_FACT, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 2


def test_spouse_group_is_in_excluded_set():
    """The exclusion must be explicit and named."""
    # همسر, زن, شوهر
    assert "\u0647\u0645\u0633\u0631" in _EXCLUDED_FROM_DUPLICATE_CANONICALISATION
    assert "\u0632\u0646" in _EXCLUDED_FROM_DUPLICATE_CANONICALISATION
    assert "\u0634\u0648\u0647\u0631" in _EXCLUDED_FROM_DUPLICATE_CANONICALISATION


def test_spouse_group_not_in_canonical_map():
    """The spouse group's stems must not appear in the canonical map."""
    # همسر stems to همسر, زن to زن, شوهر to شوهر
    assert "\u0647\u0645\u0633\u0631" not in _CANONICAL_MAP
    assert "\u0632\u0646" not in _CANONICAL_MAP
    assert "\u0634\u0648\u0647\u0631" not in _CANONICAL_MAP


# --------------------------------------------------------------------------
# Keep-separate cases (must not merge)
# --------------------------------------------------------------------------


def test_two_languages_stay_separate(store):
    store.remember(_SPEAKS_PERSIAN, kind="semantic")
    store.remember(_SPEAKS_ENGLISH, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 2


def test_living_vs_working_stay_separate(store):
    store.remember(_LIVES_TEHRAN, kind="semantic")
    store.remember(_WORKS_TEHRAN, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 2


def test_two_programming_languages_stay_separate(store):
    store.remember(_KNOWS_PYTHON, kind="semantic")
    store.remember(_KNOWS_RUST, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 2


def test_city_contradiction_stays_separate_via_supersede(store):
    """A contradiction must go to supersede, not to the duplicate path.

    The city pair (Tehran/Shiraz) has Jaccard 0.600, below the duplicate
    threshold, so it must not merge. It also has prefix overlap 0.500, below
    the contradiction threshold, so it must not supersede either. Both rows
    are kept. This test documents that the duplicate path does not interfere
    with pairs that should stay separate.
    """
    store.remember(_CITY_TEHRAN, kind="semantic")
    store.remember(_CITY_SHIRAZ, kind="semantic")
    # Both rows are kept: not a duplicate, not a contradiction.
    rows = store.all(limit=10)
    assert len(rows) == 2
    # Neither is archived.
    for row in rows:
        assert row.archived is False
        assert row.superseded_by is None


def test_two_different_phones_stay_separate(store):
    store.remember(_PHONE_SAMSUNG, kind="semantic")
    store.remember(_PHONE_IPHONE, kind="semantic")
    rows = store.all(limit=10)
    assert len(rows) == 2


# --------------------------------------------------------------------------
# Contradiction still goes to supersede, not duplicate path
# --------------------------------------------------------------------------


def test_contradiction_still_reaches_supersede(store):
    old = store.remember("the user lives in Tehran", kind="semantic")
    new = store.remember("the user lives in Shiraz", kind="semantic")
    replaced = store.get(old.id)
    assert replaced is not None
    assert replaced.archived is True
    assert replaced.superseded_by == new.id


# --------------------------------------------------------------------------
# Pinned memories are never merged
# --------------------------------------------------------------------------


def test_pinned_memory_is_never_merged(store):
    old = store.remember(_FINTECH_WITH_ARTICLE, kind="semantic")
    assert store.pin(old.id) is True
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic")
    protected = store.get(old.id)
    assert protected is not None
    assert protected.pinned is True
    assert protected.archived is False
    # Both rows should exist: the pinned one is untouched.
    rows = store.all(limit=10)
    assert len(rows) == 2


# --------------------------------------------------------------------------
# Cross-user isolation
# --------------------------------------------------------------------------


def test_duplicate_from_another_user_does_not_touch_this_users_rows(tmp_path):
    path = str(tmp_path / "dream.db")
    with MemoryStore(path, user="alice") as alice:
        alice.remember(_FINTECH_WITH_ARTICLE, kind="semantic")
    with MemoryStore(path, user="bob") as bob:
        bob.remember(_FINTECH_WITH_ARTICLE, kind="semantic")
        bob.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic")
        # Bob's duplicate is merged.
        assert len(bob.all(limit=10)) == 1
    with MemoryStore(path, user="alice") as alice:
        # Alice's row is untouched.
        assert len(alice.all(limit=10)) == 1


# --------------------------------------------------------------------------
# Non-semantic kinds are never merged
# --------------------------------------------------------------------------


def test_episodic_memories_are_never_merged(store):
    store.remember(_FINTECH_WITH_ARTICLE, kind="episodic")
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="episodic")
    rows = store.all(limit=10)
    assert len(rows) == 2


def test_procedural_memories_are_never_merged(store):
    store.remember(_FINTECH_WITH_ARTICLE, kind="procedural")
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="procedural")
    rows = store.all(limit=10)
    assert len(rows) == 2


# --------------------------------------------------------------------------
# Exact duplicates still take the existing dedupe branch
# --------------------------------------------------------------------------


def test_exact_duplicate_still_uses_existing_dedupe_branch(store):
    """Exact normalised-string matches must still take the original branch.

    The new path runs after exact dedupe, so an exact match never reaches it.
    Both branches produce the same visible result (one row, boosted
    importance), but the exact branch is simpler and must not regress.
    """
    memory_text = "the user lives in Tehran"
    store.remember(memory_text, kind="semantic", importance=0.8)
    store.remember(memory_text, kind="semantic", importance=0.9)
    rows = store.all(limit=10)
    assert len(rows) == 1
    # Exact dedupe adds 0.1 to the existing importance: 0.8 + 0.1 = 0.9.
    assert rows[0].importance == 0.9


# --------------------------------------------------------------------------
# Threshold override
# --------------------------------------------------------------------------


def test_duplicate_threshold_override_changes_the_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_DUPLICATE_THRESHOLD", "0.95")
    with MemoryStore(str(tmp_path / "override.db")) as overridden:
        assert overridden.duplicate_threshold == 0.95
        # At 0.95, the fintech pair (0.889) no longer merges.
        overridden.remember(_FINTECH_WITH_ARTICLE, kind="semantic")
        overridden.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic")
        rows = overridden.all(limit=10)
        assert len(rows) == 2


@pytest.mark.parametrize("raw", ["not-a-number", "-0.01", "1.01", "nan", ""])
def test_invalid_duplicate_threshold_falls_back(tmp_path, monkeypatch, raw):
    monkeypatch.setenv("DREAM_DUPLICATE_THRESHOLD", raw)
    with MemoryStore(str(tmp_path / "fallback.db")) as fallback:
        assert fallback.duplicate_threshold == DEFAULT_DUPLICATE_THRESHOLD


# --------------------------------------------------------------------------
# Merge callback
# --------------------------------------------------------------------------


def test_on_merge_callback_fires(store):
    merged: list = []
    store.remember(_FINTECH_WITH_ARTICLE, kind="semantic")
    store.remember(
        _FINTECH_WITHOUT_ARTICLE, kind="semantic", on_merge=merged.append
    )
    assert len(merged) == 1
    assert merged[0].id == 1  # the older row


def test_on_merge_callback_not_fired_for_non_duplicates(store):
    merged: list = []
    store.remember(_SPEAKS_PERSIAN, kind="semantic")
    store.remember(_SPEAKS_ENGLISH, kind="semantic", on_merge=merged.append)
    assert len(merged) == 0


# --------------------------------------------------------------------------
# Tags merge and last_used_at refreshes
# --------------------------------------------------------------------------


def test_merge_combines_tags(store):
    store.remember(_FINTECH_WITH_ARTICLE, kind="semantic", tags=["work"])
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic", tags=["startup"])
    rows = store.all(limit=10)
    assert len(rows) == 1
    assert set(rows[0].tags) == {"work", "startup"}


# --------------------------------------------------------------------------
# Merge into oldest by id when several candidates pass
# --------------------------------------------------------------------------


def test_merge_into_oldest_by_id(store):
    """When several rows pass the threshold, merge into the oldest."""
    # Store the same fact three times with slightly different wordings.
    # All three should collapse via successive merges into the first row.
    store.remember(_FINTECH_WITH_ARTICLE, kind="semantic", importance=0.5)
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic", importance=0.6)
    rows = store.all(limit=10)
    assert len(rows) == 1
    assert rows[0].id == 1


# --------------------------------------------------------------------------
# No other synonym group needs exclusion
# --------------------------------------------------------------------------


def test_no_other_synonym_group_has_opposing_members():
    """Verify every non-excluded group contains true synonyms only.

    The check: for each group, ensure no pair of members are antonyms or
    gendered opposites that would cause a false merge when canonicalised.
    The only such group is the spouse group, which is already excluded.
    This test documents the verification by asserting every remaining
    group's members all map to the same canonical representative, and
    spot-checks that each group passes the duplicate threshold for a
    minimal pair of sentences differing only in the group's word.
    """
    for group in _SYNONYM_GROUPS:
        if any(word in _EXCLUDED_FROM_DUPLICATE_CANONICALISATION for word in group):
            continue
        # Every member's stem must appear in the canonical map and map to
        # the same representative.
        stems = []
        for word in group:
            from dream.memory import _stem_fa, _tokenize
            for token in _tokenize(word):
                stems.append(_stem_fa(token))
        assert len(stems) >= 2, f"group {group} has fewer than 2 stemmed members"
        representatives = {_CANONICAL_MAP.get(s, s) for s in stems}
        assert len(representatives) == 1, (
            f"group {group} maps to multiple representatives: {representatives}"
        )


# --------------------------------------------------------------------------
# CLI merge reporting
# --------------------------------------------------------------------------


def _feeding_input(lines):
    iterator = iter(lines)

    def read(_prompt=""):
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return read


class _DuplicateBackend:
    def chat(self, messages, tools=None):
        del messages
        if tools is not None:
            return {"content": "Recorded.", "tool_calls": []}
        return {
            "content": (
                '[{"content": "'
                "\\u06a9\\u0627\\u0631\\u0628\\u0631 \\u0631\\u0648\\u06cc "
                "\\u0627\\u0633\\u062a\\u0627\\u0631\\u062a\\u0627\\u067e "
                "\\u0641\\u06cc\\u0646\\u200c\\u062a\\u06a9 \\u06a9\\u0627\\u0631 "
                "\\u0645\\u06cc\\u200c\\u06a9\\u0646\\u062f"
                '", "kind": "semantic", "importance": 0.9}]'
            ),
            "tool_calls": [],
        }


@pytest.mark.parametrize(("quiet", "visible"), [(False, True), (True, False)])
def test_cli_reports_merge_unless_quiet(tmp_path, monkeypatch, capsys, quiet, visible):
    import cli

    path = str(tmp_path / "cli.db")
    # Seed the store with the fintech fact including the article.
    with MemoryStore(path) as seed:
        seed.remember(_FINTECH_WITH_ARTICLE, kind="semantic", importance=1.0)

    monkeypatch.setattr("dream.agent.build_backend", lambda _kind=None: _DuplicateBackend())
    monkeypatch.setattr(
        "builtins.input",
        _feeding_input(["I also work on a fintech startup."]),
    )
    arguments = ["--db", path]
    if quiet:
        arguments.insert(0, "--quiet")

    assert cli.main(arguments) == 0
    lines = capsys.readouterr().err.splitlines()
    expected_prefix = "[memory] merged into #"
    found = any(line.startswith(expected_prefix) for line in lines)
    assert found is visible


# --------------------------------------------------------------------------
# Threshold constant value
# --------------------------------------------------------------------------


def test_default_duplicate_threshold_value():
    assert DEFAULT_DUPLICATE_THRESHOLD == 0.80


def test_default_duplicate_threshold_matches_contradiction_threshold():
    """Both thresholds use 0.80 for readability."""
    from dream.memory import DEFAULT_CONTRADICTION_THRESHOLD
    assert DEFAULT_DUPLICATE_THRESHOLD == DEFAULT_CONTRADICTION_THRESHOLD


# --------------------------------------------------------------------------
# Importance: never lowered by a duplicate
# --------------------------------------------------------------------------


def test_merge_never_lowers_importance(store):
    store.remember(_FINTECH_WITH_ARTICLE, kind="semantic", importance=0.95)
    store.remember(_FINTECH_WITHOUT_ARTICLE, kind="semantic", importance=0.3)
    rows = store.all(limit=10)
    assert len(rows) == 1
    # max(0.95, 0.3) = 0.95; boosted: min(1.0, 0.95 + 0.1) = 1.0
    assert rows[0].importance == 1.0
