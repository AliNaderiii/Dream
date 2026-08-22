"""MEM Stage B — FTS5 session search: unit, lifecycle, and failure tests.

Marquee property, both directions: a query spelled with Arabic code points
(كتاب) finds sessions written with Farsi forms (کتاب) and vice versa, plus
digit folding, ZWNJ handling, diacritic insensitivity, ranking determinism,
original-text snippets, fail-closed corruption paths, and the append-event
lifecycle. Persian literals are unescaped in test files by convention.
"""

from __future__ import annotations

import sqlite3

import pytest

from dream.session_search import (
    DEFAULT_SESSION_INDEX_PATH,
    SCHEMA_VERSION,
    SessionIndexError,
    SessionSearchIndex,
    extract_snippet,
    query_tokens,
)


@pytest.fixture()
def index(tmp_path):
    idx = SessionSearchIndex(str(tmp_path / "sessions.db"))
    yield idx
    idx.close()


# ---------------------------------------------------------------------------
# Query normalisation
# ---------------------------------------------------------------------------


def test_query_tokens_use_the_shared_normalizer():

    assert query_tokens("كتاب") == ["کتاب"]
    assert query_tokens("ساعت ۱۵") == ["ساعت", "15"]
    # Latin case is preserved by the normalizer (a Persian normalizer);
    # unicode61 case-folds at index/match time, so search is case-blind.
    assert query_tokens("mix حالة English") == ["mix", "حاله", "English"]
    assert query_tokens("   ") == []
    assert len(query_tokens(" ".join(f"w{i}" for i in range(40)))) == 12


def test_normalizer_and_tokenizer_are_the_shared_implementation():
    import dream.memory
    from dream import session_search

    assert session_search.normalize_fa is dream.memory.normalize_fa


# ---------------------------------------------------------------------------
# Marquee property: spelling variants, both directions
# ---------------------------------------------------------------------------


def test_arabic_query_finds_farsi_sessions_and_vice_versa(index):
    # The bare word in each script — the variant-folding property this stage
    # exists for. (ال-prefixed forms are morphology, not spelling variance.)
    index.index_session(
        "farsi", "یادداشت روزانه", ["من امروز یک کتاب خیلی خوب خواندم"]
    )
    index.index_session("arabic", "مكتبه", ["قرأت هذا كتاب جميلا بالعربية"])
    farsi_found = {hit.session_id for hit in index.search("كتاب")}
    arabic_found = {hit.session_id for hit in index.search("کتاب")}
    assert farsi_found == {"farsi", "arabic"}
    assert arabic_found == {"farsi", "arabic"}


def test_digit_folding_both_directions(index):
    index.index_session("persian-digits", "قرار", ["قرار ساعت ۱۵ در کافه است"])
    index.index_session("ascii-digits", "meeting", ["meeting at 15:00 sharp"])
    # OR semantics: "ساعت 15" matches either token; the doc with both wins.
    hits = index.search("ساعت 15")
    assert hits[0].session_id == "persian-digits"
    assert {h.session_id for h in hits} == {"persian-digits", "ascii-digits"}
    assert {h.session_id for h in index.search("۱۵")} == {
        "persian-digits",
        "ascii-digits",
    }


def test_zwnj_and_space_are_interchangeable(index):
    index.index_session("zwnj", "آزمایش", ["من می‌خواهم کتاب بخوانم"])
    assert any(h.session_id == "zwnj" for h in index.search("می خواهم"))
    index.index_session("spaced", "آزمایش", ["تو می روی به خانه"])
    assert any(h.session_id == "spaced" for h in index.search("می‌روی"))


def test_diacritics_are_ignored(index):
    index.index_session("diacritics", "قرآن", ["این كِتابِ قدیمی است"])
    assert any(h.session_id == "diacritics" for h in index.search("کتاب"))
    assert any(h.session_id == "diacritics" for h in index.search("كتاب"))


def test_mixed_persian_english_queries(index):
    index.index_session(
        "mixed", "release notes", ["نسخهٔ جدید release شد with deployment notes"]
    )
    hits = index.search("release deployment")
    assert hits and hits[0].session_id == "mixed"


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_more_mentions_rank_above_fewer(index):
    index.index_session(
        "frequent", "work log", ["coffee then coffee and more coffee, coffee!"]
    )
    index.index_session("single", "diary", ["one coffee today"])
    index.index_session("unrelated", "other", ["tea and water only"])
    hits = index.search("coffee")
    assert [h.session_id for h in hits] == ["frequent", "single"]


def test_title_hits_outrank_body_hits(index):
    index.index_session("in-body", "daily log", ["elephant in the room today"])
    index.index_session("in-title", "elephant migration", ["we watched them pass"])
    hits = index.search("elephant")
    assert hits[0].session_id == "in-title"
    assert hits[0].matched_in_title is True
    assert hits[1].matched_in_title is False


def test_equal_scores_tie_break_newest_first_and_stably(index):
    for sid in ("old", "new1", "new2"):
        index.index_session(sid, "log", ["alpha bravo charlie delta echo"])
    first = [h.session_id for h in index.search("alpha")]
    second = [h.session_id for h in index.search("alpha")]
    assert first == second  # deterministic
    assert first == ["new2", "new1", "old"]  # id DESC = newest first


def test_scores_are_positive_and_sorted_descending(index):
    index.index_session("a", "t", ["giraffe a b c d e f g h"])
    index.index_session("b", "t", ["giraffe giraffe a b c d e f"])
    hits = index.search("giraffe")
    scores = [h.score for h in hits]
    assert all(score > 0 for score in scores)
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Snippets from the ORIGINAL text
# ---------------------------------------------------------------------------


def _strip_markers(snippet: str) -> str:
    return snippet.replace("[", "").replace("]", "")


def test_snippet_highlights_the_original_spelling_not_the_shadow(index):
    index.index_session("orig", "title", ["من كتاب فروشی را دیدم و کتاب خریدم"])
    hit = index.search("کتاب")[0]
    # The bracketed word is the session's OWN spelling (Arabic yeh/kaf here),
    # not the normalised Farsi shadow the index stores.
    bracketed = hit.snippet[hit.snippet.index("[") + 1 : hit.snippet.index("]")]
    assert bracketed in {"كتاب", "كتاب‌فروشی", "كتاب فروشی"} or "كتاب" in bracketed
    assert "ك" in bracketed  # Arabic kaf survives verbatim


def test_snippet_is_a_verbatim_slice_of_the_original():
    original = "start of a long Persian sentence دربارهٔ گزارش سالانه و مدیریت داده‌ها end"
    snippet = extract_snippet(original, "گزارش", width=30)
    body = _strip_markers(snippet)
    assert body.lstrip("…").rstrip("…") in original


def test_snippet_boundaries_land_on_word_edges():
    original = "one two three four five six seven eight nine ten eleven twelve"
    snippet = extract_snippet(original, "seven", width=15)
    body = _strip_markers(snippet).lstrip("…").rstrip("…")
    first_word = body.split(" ", 1)[0]
    last_word = body.rsplit(" ", 1)[1]
    assert first_word in original.split()
    assert last_word in original.split()
    # The whole clipped body is word-aligned: no partial words.
    assert body in original


def test_snippet_does_not_mangle_rtl_mixed_content():
    original = "latin prefix جملهٔ فارسی با کتاب و mixed english tokens in middle"
    snippet = extract_snippet(original, "کتاب")
    body = _strip_markers(snippet).lstrip("…").rstrip("…")
    assert body in original  # contiguous slice — nothing reordered
    assert "[کتاب]" in snippet


def test_snippet_marks_every_matching_word_in_the_window():
    original = "alpha coffee beta coffee gamma coffee delta"
    snippet = extract_snippet(original, "coffee", width=40)
    assert snippet.count("[coffee]") == 3


def test_snippet_without_a_match_clips_the_head_at_a_word_edge():
    original = "پاراگراف بلند بدون هیچ تطابقی در این جمله وجود دارد ادامه متن"
    snippet = extract_snippet(original, "zzz-absent", width=12)
    assert snippet.endswith("…")
    assert "[" not in snippet
    assert _strip_markers(snippet).rstrip("…") in original


def test_short_text_snippet_returns_whole_text():
    original = "کوتاه"
    assert extract_snippet(original, "کوتاه") == "[کوتاه]"


# ---------------------------------------------------------------------------
# Lifecycle: index / append / remove / rebuild / persistence
# ---------------------------------------------------------------------------


def test_index_session_is_an_idempotent_upsert(index):
    index.index_session("s", "first title", ["first message"])
    index.index_session("s", "second title", ["replaced message"])
    assert index.doc_count() == 1
    hits = index.search("replaced")
    assert len(hits) == 1
    assert hits[0].title == "second title"
    assert {h.session_id for h in index.search("first")} == set()


def test_append_message_grows_the_document(index):
    index.index_session("chat", "project", ["первое" if False else "first turn"])
    index.append_message("chat", "ساعت ۱۵ قرار داریم")
    index.append_message("chat", "third turn about deployment")
    assert index.doc_count() == 1
    assert any(h.session_id == "chat" for h in index.search("deployment"))
    assert any(h.session_id == "chat" for h in index.search("قرار"))
    assert not any(h.session_id == "chat" for h in index.search("absent-word"))


def test_append_message_creates_a_new_document_when_unknown(index):
    index.append_message("fresh", "brand new message about quantum")
    assert index.doc_count() == 1
    hits = index.search("quantum")
    assert hits and hits[0].session_id == "fresh"


def test_remove_session_deletes_and_unindexes(index):
    index.index_session("gone", "t", [" ephemeral content here"])
    assert index.remove_session("gone") is True
    assert index.doc_count() == 0
    assert index.search("ephemeral") == []
    assert index.remove_session("gone") is False


def test_rebuild_rederives_the_index_from_content(index):
    index.index_session("keep", "kept title", ["kept message about saffron"])
    before = index.search("saffron")
    count = index.rebuild()
    assert count == 1
    after = index.search("saffron")
    assert [h.session_id for h in after] == [h.session_id for h in before]
    assert after[0].title == "kept title"


def test_documents_survive_reopen(tmp_path):
    path = str(tmp_path / "sessions.db")
    with SessionSearchIndex(path) as first:
        first.index_session("persist", "عنوان ماندگار", ["پیام ماندگار دربارهٔ زعفران"])
    with SessionSearchIndex(path) as second:
        hits = second.search("زعفران")
        assert hits and hits[0].session_id == "persist"
        assert hits[0].title == "عنوان ماندگار"


def test_paging_with_limit_and_offset(index):
    for i in range(5):
        index.index_session(f"s{i}", f"log {i}", [f"needle occurrence number {i}"])
    page_one = index.search("needle", limit=2)
    page_two = index.search("needle", limit=2, offset=2)
    assert len(page_one) == 2
    assert len(page_two) == 2
    assert {h.session_id for h in page_one}.isdisjoint({h.session_id for h in page_two})


def test_empty_query_fails_with_bilingual_error(index):
    with pytest.raises(SessionIndexError) as excinfo:
        index.search("   \u064b  ")  # whitespace + a bare diacritic
    message = str(excinfo.value)
    assert "عبارت جست‌وجو" in message
    assert "Query normalizes to no searchable tokens" in message


def test_invalid_session_id_is_rejected(index):
    with pytest.raises(ValueError):
        index.index_session("  ", "t", ["m"])


# ---------------------------------------------------------------------------
# Fail-closed open: missing is fresh, corrupt/mismatched refuses
# ---------------------------------------------------------------------------


def test_missing_file_initialises_fresh(tmp_path):
    fresh = SessionSearchIndex(str(tmp_path / "new.db"))
    try:
        assert fresh.doc_count() == 0
        version = fresh.conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        fresh.close()


def test_default_path_lives_under_the_data_directory():
    assert DEFAULT_SESSION_INDEX_PATH.startswith("data/")
    assert DEFAULT_SESSION_INDEX_PATH.endswith(".db")


def test_env_override_is_honoured(tmp_path, monkeypatch):
    import os

    override = str(tmp_path / "env-index.db")
    monkeypatch.setenv("DREAM_SESSION_INDEX_DB", override)
    import dream.session_search as module

    assert module.DEFAULT_SESSION_INDEX_PATH == "data/dream-session-index.db"
    # The override is consumed by callers at construction (Stage F wiring);
    # the kernel accepts any explicit path, pinned here.
    with SessionSearchIndex(override) as idx:
        idx.index_session("env", "t", ["env-pinned message"])
    assert os.path.exists(override)


def _expect_fail_closed(path: str) -> SessionIndexError:
    with pytest.raises(SessionIndexError) as excinfo:
        SessionSearchIndex(path)
    message = str(excinfo.value)
    # Bilingual: Persian guidance plus the English rebuild sentence.
    assert "\u0627\u06cc\u0646\u062f\u06a9\u0633" in message  # «ایندکس»
    assert "rebuild" in message
    assert excinfo.value.details["path"] == path
    return excinfo.value


def test_garbage_file_fails_closed_bilingually(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is definitely not a sqlite database, sorry")
    error = _expect_fail_closed(str(bad))
    assert error.details["reason"].startswith("unreadable")


def test_future_schema_version_fails_closed(tmp_path):
    path = str(tmp_path / "future.db")
    SessionSearchIndex(path).close()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    error = _expect_fail_closed(path)
    assert error.details["reason"] == "schema version mismatch"
    assert error.details["found"] == SCHEMA_VERSION + 1
    assert error.details["expected"] == SCHEMA_VERSION


def test_structurally_incomplete_index_fails_closed(tmp_path):
    path = str(tmp_path / "incomplete.db")
    SessionSearchIndex(path).close()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE session_fts")
    conn.commit()
    conn.close()
    error = _expect_fail_closed(path)
    assert error.details["reason"] == "structurally incomplete"
    assert error.details["missing"] == ["session_fts"]


def test_tables_without_version_stamp_fail_closed(tmp_path):
    path = str(tmp_path / "unstamped.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE session_docs (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    error = _expect_fail_closed(path)
    assert error.details["reason"] == "tables present without a schema version stamp"


def test_corruption_is_never_silently_wiped(tmp_path):
    """A refused open must leave the file byte-identical."""
    bad = tmp_path / "precious.db"
    payload = b"CORRUPT-BUT-MINE" * 32
    bad.write_bytes(payload)
    with pytest.raises(SessionIndexError):
        SessionSearchIndex(str(bad))
    assert bad.read_bytes() == payload
