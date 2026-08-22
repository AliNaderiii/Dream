"""MEM Stage B — Gate B performance benchmark on a 10,000-session corpus.

Synthetic but realistic: mixed Persian/English sentences, Arabic-variant
spellings on a known subset of sessions, Persian digits, ZWNJ verbs, and
occasional diacritics.  Deterministic seed — every run indexes the same
corpus.  Cold (first query after open) and warm query latency are measured
in the Gate A format (min/p50/p95/max) against the 50 ms budget.

Run verbosely to capture the benchmark block for MEM-GATES.md:
    .venv/bin/python -m pytest tests/test_session_search_perf.py -s -q
"""

from __future__ import annotations

import os
import random
import statistics
import time

import pytest

from dream.session_search import SessionSearchIndex

CORPUS_SIZE = 10_000
BUDGET_MS = 50.0

# Deterministic corpus vocabulary. Persian bank (plain Farsi spellings).
# NOTE: the probe word کتاب is deliberately absent from this bank — it is
# injected only into the known needle sessions so recall is exactly countable.
_FA_WORDS = [
    "گزارش", "مالی", "پروژه", "جلسه", "قرار", "ساعت", "فردا", "امروز",
    "دیروز", "هفته", "ماه", "سال", "مشتری", "کاربر", "داده", "تحلیل", "نتیجه",
    "مسئله", "راه", "حل", "زمان", "برنامه", "تقویم", "یادداشت", "خلاصه", "لیست",
    "قیمت", "سهم", "بازار", "تهران", "شیراز", "دانشگاه", "درس", "امتحان",
]
# Arabic-codepoint variants swapped in for a subset of sessions: Arabic yeh
# (U+064A) and kaf (U+0643) replace Farsi yeh (U+06CC) and keheh (U+06A9).
# The probe pair lives only in the needle injection, not the general bank.
_AR_VARIANTS = {
    "مسئله": "مسئلة",
    "جلسه": "جلسة",
    "نتیجه": "نتيجة",
    "راه": "طريق",
}
_EN_WORDS = [
    "deployment", "pipeline", "release", "meeting", "report", "database",
    "schema", "migration", "review", "sprint", "backlog", "endpoint",
    "latency", "budget", "memory", "kernel", "session", "search", "index",
    "snapshot", "approval", "gateway", "scheduler", "provider", "ledger",
]
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

# Every 84th session (deterministic) mentions the book word: half written
# with Arabic code points, half with Farsi — the marquee recall probe.
NEEDLE_INTERVAL = 84
NEEDLE_FA = "کتاب"
NEEDLE_AR = "كتاب"


def _sentence(rng: random.Random, arabic_mode: bool) -> str:
    words: list[str] = []
    length = rng.randint(8, 16)
    if arabic_mode:
        fa_pool = [_AR_VARIANTS.get(w, w) for w in _FA_WORDS]
    else:
        fa_pool = list(_FA_WORDS)
    for _ in range(length):
        roll = rng.random()
        if roll < 0.45:
            words.append(rng.choice(fa_pool))
        elif roll < 0.8:
            words.append(rng.choice(_EN_WORDS))
        elif roll < 0.9:
            number = "".join(rng.choice(_FA_DIGITS) for _ in range(rng.randint(1, 4)))
            words.append(number)
        else:
            words.append(rng.choice(["می‌خواهم", "می‌روم", "نمی‌شود", "بیمه‌نامه"]))
    return " ".join(words)


def build_corpus() -> list[tuple[str, str, list[str], bool]]:
    rng = random.Random(20260822)
    corpus = []
    for i in range(CORPUS_SIZE):
        is_needle = i % NEEDLE_INTERVAL == 0
        arabic_mode = is_needle and (i // NEEDLE_INTERVAL) % 2 == 0
        title_words = [_sentence(rng, arabic_mode) for _ in range(2)]
        title = " ".join(title_words)[:80]
        messages = [_sentence(rng, arabic_mode) for _ in range(5)]
        if is_needle:
            marker = NEEDLE_AR if arabic_mode else NEEDLE_FA
            position = rng.randint(0, len(messages) - 1)
            messages[position] = f"{messages[position]} {marker} خواندنی بود"
        corpus.append((f"sess_{i:05d}", title, messages, arabic_mode))
    return corpus


def _percentile(samples: list[float], pct: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def _report(label: str, samples_ms: list[float]) -> None:
    print(
        f"{label}: n={len(samples_ms)} "
        f"min={min(samples_ms):.3f} p50={statistics.median(samples_ms):.3f} "
        f"p95={_percentile(samples_ms, 95):.3f} max={max(samples_ms):.3f} "
        f"budget_ms={BUDGET_MS:.0f}"
    )


QUERIES = [
    "كتاب",  # Arabic codepoints
    "کتاب",  # Farsi codepoints
    "گزارش مالی",
    "deployment pipeline",
    "ساعت ۱۵",
    "می‌خواهم",
    "بازار تهران",
    "migration review",
    "جلسه فردا report",
    "snapshot memory kernel",
]


@pytest.fixture(scope="module")
def corpus_db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("perf") / "sessions-10k.db")
    corpus = build_corpus()
    index = SessionSearchIndex(path)
    started = time.perf_counter()
    for session_id, title, messages, _ in corpus:
        index.index_session(session_id, title, messages, source="synthetic")
    build_seconds = time.perf_counter() - started
    print(f"corpus_sessions={CORPUS_SIZE} index_build_seconds={build_seconds:.2f}")
    print(f"db_size_mb={os.path.getsize(path) / (1024 * 1024):.1f}")
    assert index.doc_count() == CORPUS_SIZE
    yield path, corpus
    index.close()


def test_marquee_recall_on_the_10k_corpus(corpus_db):
    path, corpus = corpus_db
    expected_needle = sum(1 for i in range(CORPUS_SIZE) if i % NEEDLE_INTERVAL == 0)
    with SessionSearchIndex(path) as index:
        arabic_hits = {h.session_id for h in index.search(NEEDLE_AR, limit=5000)}
        farsi_hits = {h.session_id for h in index.search(NEEDLE_FA, limit=5000)}
    assert len(arabic_hits) == expected_needle
    assert len(farsi_hits) == expected_needle
    assert arabic_hits == farsi_hits  # both spellings reach every needle session


def test_query_latency_cold_and_warm_under_budget(corpus_db):
    path, _corpus = corpus_db

    # Cold: first query after each of 10 fresh opens.
    cold_ms: list[float] = []
    for i in range(10):
        with SessionSearchIndex(path) as index:
            started = time.perf_counter()
            index.search(QUERIES[i % len(QUERIES)], limit=20)
            cold_ms.append((time.perf_counter() - started) * 1000)
    _report("query_cold_ms", cold_ms)

    # Warm: 200 queries cycling the bilingual battery.
    with SessionSearchIndex(path) as index:
        warm_ms: list[float] = []
        for i in range(200):
            query = QUERIES[i % len(QUERIES)]
            started = time.perf_counter()
            index.search(query, limit=20)
            warm_ms.append((time.perf_counter() - started) * 1000)
    _report("query_warm_ms", warm_ms)

    assert _percentile(cold_ms, 95) < BUDGET_MS, cold_ms
    assert _percentile(warm_ms, 95) < BUDGET_MS, warm_ms
    assert statistics.median(warm_ms) < BUDGET_MS, warm_ms
    # The battery actually returns results (a fast empty answer is not a pass).
    with SessionSearchIndex(path) as index:
        assert index.search("كتاب", limit=5)
        assert index.search("deployment", limit=5)
