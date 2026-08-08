"""Tests for Persian synonym expansion in the FTS query builder.

Lexical search matches words, not meaning: the store once held a memory
written with one word for "name" and could not find it when the question
used the other, because the stemmed tokens share nothing. These tests pin
the synonym table that closes that gap, its shape, the DREAM_SYNONYMS
override file, and — above all — that expansion never outranks an exact
match for the same query.

New Persian strings in this module are written as backslash-u escapes,
matching tests/test_extraction_prompt.py, so they cannot be corrupted in
transit.
"""

from __future__ import annotations

import json

import pytest

import dream.memory
from dream.memory import (
    _SYNONYM_GROUPS,
    MemoryStore,
    _build_synonym_index,
    _load_extra_synonym_groups,
    _stem_fa,
    _tokenize,
    build_match_query,
)


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


# The observed fault, as escapes:
# کاربر علی نام دارد / اسم من چیه؟ / نام من چیست؟
_NAME_MEMORY = (
    "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc "
    "\u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
)
_ASK_NAME_COLOQUIAL = "\u0627\u0633\u0645 \u0645\u0646 \u0686\u06cc\u0647\u061f"
_ASK_NAME_FORMAL = "\u0646\u0627\u0645 \u0645\u0646 \u0686\u06cc\u0633\u062a\u061f"


def test_observed_bug_both_spellings_of_the_question_find_the_memory(store):
    """The reported regression: asked the name with the colloquial word the
    store found nothing, while the formal word worked. Both must recall."""
    store.remember(_NAME_MEMORY, kind="semantic", importance=1.0)
    for question in (_ASK_NAME_COLOQUIAL, _ASK_NAME_FORMAL):
        found = [m.content for m in store.recall(question, reinforce=False)]
        assert _NAME_MEMORY in found, f"not recalled for: {question}"


# --------------------------------------------------------------------------
# Expansion must not change queries the table does not know
# --------------------------------------------------------------------------


def test_unknown_tokens_build_exactly_the_pre_expansion_query():
    # قهوه تلخ (bitter coffee): neither token sits in the synonym table, so
    # the MATCH expression must be exactly the old exact-term-plus-prefix
    # shape and nothing more.
    coffee = "\u0642\u0647\u0648\u0647"
    bitter = "\u062a\u0644\u062e"
    expected = f'"{coffee}" OR "{coffee}"* OR "{bitter}" OR "{bitter}"*'
    assert build_match_query(f"{coffee} {bitter}") == expected


# --------------------------------------------------------------------------
# Inflected forms reach the table through their stems
# --------------------------------------------------------------------------


def test_inflected_form_of_a_table_word_still_expands(store):
    # خودروم چیست؟ (what is my car?) — خودروم is خودرو with the possessive
    # suffix; the stem must still hit the car group and reach ماشین.
    car_group_member = "\u0645\u0627\u0634\u06cc\u0646"
    expression = build_match_query("\u062e\u0648\u062f\u0631\u0648\u0645 \u0686\u06cc\u0633\u062a")
    assert f'"{car_group_member}" OR' in expression

    # And end to end: a memory stored with ماشین answers a خودرو question.
    # ماشین کاربر پژو است
    car_memory = (
        "\u0645\u0627\u0634\u06cc\u0646 \u06a9\u0627\u0631\u0628\u0631 "
        "\u067e\u0698\u0648 \u0627\u0633\u062a"
    )
    store.remember(car_memory, kind="semantic", importance=0.9)
    hits = store.recall("\u062e\u0648\u062f\u0631\u0648\u0645", reinforce=False)
    assert car_memory in [m.content for m in hits]


def test_empty_and_punctuation_only_queries_never_raise(store):
    assert build_match_query("") == ""
    assert build_match_query("\u061f\u061f\u061f \u2026 \u060c\u060c") == ""
    assert store.recall("", reinforce=False) == []
    assert store.recall("\u061f\u061f\u061f !!! ...", reinforce=False) == []


# --------------------------------------------------------------------------
# The DREAM_SYNONYMS override file
# --------------------------------------------------------------------------

# برادر / داداش (brother, colloquial brother) — an extra group used to
# exercise the override file.
_EXTRA_GROUP = ["\u0628\u0631\u0627\u062f\u0631", "\u062f\u0627\u062f\u0627\u0634"]


def test_environment_override_loads_extra_groups(tmp_path, monkeypatch):
    path = tmp_path / "extra.json"
    path.write_text(json.dumps([_EXTRA_GROUP], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("DREAM_SYNONYMS", str(path))

    extra = _load_extra_synonym_groups()
    assert extra == (tuple(_EXTRA_GROUP),)

    merged = _build_synonym_index((*_SYNONYM_GROUPS, *extra))
    monkeypatch.setattr(dream.memory, "_SYNONYM_INDEX", merged)

    # برادر من (my brother) now reaches داداش — indexed under its stem داد,
    # as the single-suffix stemmer leaves it ...
    brother_clauses = build_match_query("\u0628\u0631\u0627\u062f\u0631 \u0645\u0646").split(" OR ")
    assert '"\u062f\u0627\u062f"' in brother_clauses
    # ... and the built-in groups keep working alongside the extra one:
    # اسم (name) still expands to نام.
    assert '"\u0646\u0627\u0645"' in build_match_query("\u0627\u0633\u0645").split(" OR ")


def test_environment_override_unset_loads_nothing(monkeypatch):
    monkeypatch.delenv("DREAM_SYNONYMS", raising=False)
    assert _load_extra_synonym_groups() == ()


def test_missing_override_path_falls_back_silently(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_SYNONYMS", str(tmp_path / "does-not-exist.json"))
    assert _load_extra_synonym_groups() == ()


def test_unreadable_override_path_falls_back_silently(tmp_path, monkeypatch):
    # A directory cannot be opened as a file.
    monkeypatch.setenv("DREAM_SYNONYMS", str(tmp_path))
    assert _load_extra_synonym_groups() == ()


def test_malformed_override_json_falls_back_silently(tmp_path, monkeypatch):
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("DREAM_SYNONYMS", str(path))
    assert _load_extra_synonym_groups() == ()


@pytest.mark.parametrize(
    "payload",
    [
        '{"a": 1}',  # not a list at all
        '["\u0633\u0644\u0627\u0645"]',  # inner entries are not lists
        '[["\u062e\u0648\u0628", 5]]',  # a group member is not a string
    ],
)
def test_wrong_shaped_override_file_falls_back_silently(tmp_path, monkeypatch, payload):
    path = tmp_path / "wrong-shape.json"
    path.write_text(payload, encoding="utf-8")
    monkeypatch.setenv("DREAM_SYNONYMS", str(path))
    assert _load_extra_synonym_groups() == ()


# --------------------------------------------------------------------------
# The table is symmetric and never outranks an exact match
# --------------------------------------------------------------------------


def test_synonym_groups_are_symmetric():
    """Whichever member of a group is queried, every other member's stem
    must join the MATCH expression as an exact term."""
    for group in _SYNONYM_GROUPS:
        for member in group:
            clauses = build_match_query(member).split(" OR ")
            for other in group:
                for token in _tokenize(other):
                    stem = _stem_fa(token)
                    assert f'"{stem}"' in clauses, (
                        f"querying {member!r} does not expand to {stem!r}"
                    )


def test_synonym_match_ranks_below_exact_match_for_the_same_query(store):
    """Expansion widens recall; it must never bury the exact wording.

    One memory states the name with the very word the question uses, one
    only with its synonym, and a filler keeps the corpus honest so bm25's
    term frequencies stay meaningful. For «اسم من چیست» the exact-wording
    memory matches the query's own terms while the synonym memory matches
    only through expansion — so it must surface, but strictly below.
    """
    # اسم من علی است (my name is Ali) — matches the query terms themselves.
    exact_memory = (
        "\u0627\u0633\u0645 \u0645\u0646 \u0639\u0644\u06cc "
        "\u0627\u0633\u062a"
    )
    # نام کاربر رضا است (the user's name is Reza) — reachable only through
    # the اسم/نام synonym group.
    synonym_memory = (
        "\u0646\u0627\u0645 \u06a9\u0627\u0631\u0628\u0631 \u0631\u0636\u0627 "
        "\u0627\u0633\u062a"
    )
    # کاربر قهوه دوست دارد (the user likes coffee) — matches nothing here.
    filler_memory = (
        "\u06a9\u0627\u0631\u0628\u0631 \u0642\u0647\u0648\u0647 "
        "\u062f\u0648\u0633\u062a \u062f\u0627\u0631\u062f"
    )
    store.remember(exact_memory, kind="semantic", importance=1.0)
    store.remember(synonym_memory, kind="semantic", importance=0.5)
    store.remember(filler_memory, kind="semantic", importance=0.5)

    question = "\u0627\u0633\u0645 \u0645\u0646 \u0686\u06cc\u0633\u062a"
    results = store.recall(question, reinforce=False)
    contents = [m.content for m in results]

    assert contents, "the query must still recall something"
    assert contents[0] == exact_memory, "an exact-wording memory must rank first"
    assert synonym_memory in contents, "expansion must still surface the synonym memory"
    assert filler_memory not in contents


# --------------------------------------------------------------------------
# The who-am-I recall gap
# --------------------------------------------------------------------------


def test_who_am_i_question_reaches_name_and_work_facts(store):
    """The Persian who-am-I question reaches the name fact and the work fact.

    The owner asked «من کی هستم» (who am I) and got nothing, while «شغل من
    چیست» (what is my job) found the work fact. The gap is lexical: the
    question has no words in common with facts stored under «کاربر». The
    کی/کاربر synonym group closes that gap without widening unrelated queries.
    """
    # کاربر علی نام دارد (the user's name is Ali)
    name_fact = (
        "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc "
        "\u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
    )
    # کاربر روی یک استارتاپ فین‌تک کار می‌کند
    work_fact = (
        "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0648\u06cc \u06cc\u06a9 "
        "\u0627\u0633\u062a\u0627\u0631\u062a\u0627\u067e "
        "\u0641\u06cc\u0646\u200c\u062a\u06a9 \u06a9\u0627\u0631 "
        "\u0645\u06cc\u200c\u06a9\u0646\u062f"
    )
    store.remember(name_fact, kind="semantic", importance=0.9)
    store.remember(work_fact, kind="semantic", importance=0.9)

    # من کی هستم (who am I)
    question = "\u0645\u0646 \u06a9\u06cc \u0647\u0633\u062a\u0645"
    results = store.recall(question, reinforce=False)
    contents = [m.content for m in results]

    assert name_fact in contents, "who-am-I must reach the name fact"
    assert work_fact in contents, "who-am-I must reach the work fact"


@pytest.mark.parametrize(
    "question",
    [
        "\u0627\u0633\u0645 \u0645\u0646 \u0686\u06cc\u0647\u061f",
        "\u0646\u0627\u0645 \u06a9\u0627\u0645\u0644 \u0645\u0646 \u0686\u06cc\u0633\u062a\u061f",
        "\u0645\u0646 \u06a9\u06cc \u0647\u0633\u062a\u0645\u061f",
    ],
)
def test_full_name_recall_keeps_family_name_for_persian_name_questions(store, question):
    """Full-name storage must answer name questions with the family name intact."""
    full_name_fact = (
        "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc\u0631\u0636\u0627 "
        "\u0646\u0627\u062f\u0631\u06cc \u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
    )
    store.remember(full_name_fact, kind="semantic", importance=0.9)

    contents = [m.content for m in store.recall(question, reinforce=False)]

    assert full_name_fact in contents
    assert any("\u0646\u0627\u062f\u0631\u06cc" in content for content in contents)


def test_unrelated_query_still_does_not_match(store):
    """A query that should not match still does not.

    Adding the کی/کاربر group must not cause unrelated queries to start
    matching everything. A question about coffee should not find facts about
    the user's name or work.
    """
    # کاربر علی نام دارد (the user's name is Ali)
    name_fact = (
        "\u06a9\u0627\u0631\u0628\u0631 \u0639\u0644\u06cc "
        "\u0646\u0627\u0645 \u062f\u0627\u0631\u062f"
    )
    store.remember(name_fact, kind="semantic", importance=0.9)

    # قهوه تلخ (bitter coffee) — no overlap with the name fact
    question = "\u0642\u0647\u0648\u0647 \u062a\u0644\u062e"
    results = store.recall(question, reinforce=False)
    contents = [m.content for m in results]

    assert name_fact not in contents, "coffee query must not find name fact"
