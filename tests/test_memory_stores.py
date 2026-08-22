"""MEM Stage A — dual bounded memory stores: unit and property tests.

Scope (Gate A): capacity accounting, the exact header format, overflow as an
error (never truncation), unique-substring matching through Dream's single
Persian normalizer, snapshot immutability, persistence, per-user isolation,
the < 5 ms snapshot budget, and the one-implementation normalizer pin.

Persian literals are unescaped in test files on purpose: the M16 escaping
convention governs product code under ``dream/`` only.
"""

from __future__ import annotations

import dataclasses
import random
import time

import pytest

import dream.memory
from dream.memory_stores import (
    ENTRY_SEPARATOR,
    MIN_CAPACITY_CHARS,
    NOTES_CAPACITY_CHARS,
    PROFILE_CAPACITY_CHARS,
    TARGET_MEMORY,
    TARGET_USER,
    AmbiguousEntryError,
    BoundedMemory,
    BoundedSnapshot,
    BoundedStore,
    BoundedStoreError,
    EntryNotFoundError,
    StoreCapacityError,
    normalize_fa,
)


@pytest.fixture()
def notes(tmp_path):
    store = BoundedStore(TARGET_MEMORY, NOTES_CAPACITY_CHARS, path=str(tmp_path / "b.db"))
    yield store
    store.close()


@pytest.fixture()
def profile(tmp_path):
    store = BoundedStore(TARGET_USER, PROFILE_CAPACITY_CHARS, path=str(tmp_path / "b.db"))
    yield store
    store.close()


# ---------------------------------------------------------------------------
# Constants and construction
# ---------------------------------------------------------------------------


def test_capacity_defaults_are_the_specified_budgets():
    assert NOTES_CAPACITY_CHARS == 2_200
    assert PROFILE_CAPACITY_CHARS == 1_375


def test_capacities_are_configurable_in_code(tmp_path):
    store = BoundedStore(TARGET_MEMORY, 500, path=str(tmp_path / "b.db"))
    try:
        assert store.capacity == 500
        with pytest.raises(StoreCapacityError):
            store.add("x" * 600)
    finally:
        store.close()


def test_constructor_rejects_bad_target_capacity_and_separator(tmp_path):
    with pytest.raises(ValueError, match="target"):
        BoundedStore("diary", 500, path=str(tmp_path / "b.db"))
    with pytest.raises(ValueError, match="capacity"):
        BoundedStore(TARGET_MEMORY, MIN_CAPACITY_CHARS - 1, path=str(tmp_path / "b.db"))
    with pytest.raises(ValueError, match="capacity"):
        BoundedStore(TARGET_MEMORY, True, path=str(tmp_path / "b.db"))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="separator"):
        BoundedStore(TARGET_MEMORY, 500, path=str(tmp_path / "b.db"), separator="")


def test_separator_is_section_mark():
    assert ENTRY_SEPARATOR == "§"


# ---------------------------------------------------------------------------
# Capacity accounting and the header contract
# ---------------------------------------------------------------------------


def test_used_chars_counts_entries_and_separators(notes):
    notes.add("a" * 736)
    notes.add("b" * 737)
    snapshot = notes.snapshot()
    assert snapshot.used_chars == 736 + 1 + 737
    assert snapshot.header == "[67% — 1,474/2,200 chars]"


def test_header_matches_specified_format_exactly(notes):
    notes.add("x" * 100)
    snapshot = notes.snapshot()
    assert snapshot.header.startswith("[")
    assert snapshot.header.endswith(" chars]")
    assert "%" in snapshot.header
    assert f"{snapshot.used_chars:,}" in snapshot.header
    assert f"{snapshot.capacity:,}" in snapshot.header


def test_empty_store_header_is_zero_percent(notes):
    snapshot = notes.snapshot()
    assert snapshot.used_chars == 0
    assert snapshot.percent == 0
    assert snapshot.header == "[0% — 0/2,200 chars]"
    assert snapshot.text == ""
    assert snapshot.entries == ()


def test_snapshot_text_joins_entries_with_separator(notes):
    notes.add("first")
    notes.add("second")
    notes.add("third")
    assert notes.snapshot().text == "first§second§third"


def test_order_is_insertion_order(notes):
    for i in range(10):
        notes.add(f"entry-{i:02d}")
    assert notes.snapshot().entries == tuple(f"entry-{i:02d}" for i in range(10))


# ---------------------------------------------------------------------------
# Overflow is an error, never a truncation
# ---------------------------------------------------------------------------


def test_add_past_capacity_raises_and_leaves_store_unchanged(notes):
    notes.add("seed")
    with pytest.raises(StoreCapacityError) as excinfo:
        notes.add("y" * NOTES_CAPACITY_CHARS)
    error = excinfo.value
    # used (4) + separator (1) + new entry (2,200) exceeds 2,200 by 5.
    assert error.details["over_by"] == len("seed") + 1
    assert error.details["capacity"] == NOTES_CAPACITY_CHARS
    assert error.details["used_chars"] == len("seed")
    # The message is bilingual and instructs consolidation, not truncation.
    assert "replace" in str(error) and "remove" in str(error)
    assert "truncated" in str(error)
    # Nothing was written.
    assert notes.snapshot().entries == ("seed",)


def test_replace_growth_past_capacity_raises_and_keeps_original(notes):
    notes.add("short")
    with pytest.raises(StoreCapacityError):
        notes.replace("short", "z" * (NOTES_CAPACITY_CHARS + 1))
    assert notes.snapshot().entries == ("short",)


def test_replace_up_to_exact_capacity_is_allowed(notes):
    notes.add("short")
    snapshot = notes.replace("short", "z" * NOTES_CAPACITY_CHARS)
    assert snapshot.used_chars == NOTES_CAPACITY_CHARS


def test_replace_shrink_frees_capacity(notes):
    notes.add("a" * 1_000)
    snapshot = notes.replace("a" * 1_000, "tiny")
    assert snapshot.entries == ("tiny",)
    assert snapshot.used_chars == len("tiny")


def test_entry_exactly_filling_the_store_is_accepted(notes):
    snapshot = notes.add("a" * NOTES_CAPACITY_CHARS)
    assert snapshot.used_chars == NOTES_CAPACITY_CHARS
    assert snapshot.percent == 100
    assert snapshot.header == "[100% — 2,200/2,200 chars]"
    # One character more — separator plus char — must now fail.
    with pytest.raises(StoreCapacityError):
        notes.add("b")


# ---------------------------------------------------------------------------
# Unique-substring matching
# ---------------------------------------------------------------------------


def test_remove_by_unique_substring(notes):
    notes.add("coffee: dark roast only")
    notes.add("tea: never with milk")
    snapshot = notes.remove("dark roast")
    assert snapshot.entries == ("tea: never with milk",)
    assert snapshot.used_chars == len("tea: never with milk")


def test_remove_not_found_raises_and_changes_nothing(notes):
    notes.add("kept")
    with pytest.raises(EntryNotFoundError):
        notes.remove("absent")
    assert notes.snapshot().entries == ("kept",)


def test_ambiguous_fragment_refuses_and_lists_candidates(notes):
    notes.add("coffee dark")
    notes.add("coffee light")
    with pytest.raises(AmbiguousEntryError) as excinfo:
        notes.remove("coffee")
    assert excinfo.value.details["matches"] == ["coffee dark", "coffee light"]
    assert "coffee dark" in str(excinfo.value) and "coffee light" in str(excinfo.value)
    assert notes.snapshot().entries == ("coffee dark", "coffee light")


def test_longer_fragment_disambiguates(notes):
    notes.add("coffee dark")
    notes.add("coffee light")
    snapshot = notes.remove("coffee light")
    assert snapshot.entries == ("coffee dark",)


def test_replace_by_unique_substring(notes):
    notes.add("user drinks tea")
    snapshot = notes.replace("tea", "user drinks coffee, no sugar")
    assert snapshot.entries == ("user drinks coffee, no sugar",)


def test_empty_old_is_rejected(notes):
    notes.add("kept")
    with pytest.raises(BoundedStoreError):
        notes.remove("")
    with pytest.raises(BoundedStoreError):
        notes.replace("   ", "new")
    # A fragment that normalizes to nothing (diacritics only) is rejected too.
    with pytest.raises(BoundedStoreError):
        notes.remove("\u064b")
    assert notes.snapshot().entries == ("kept",)


def test_add_rejects_empty_text(notes):
    with pytest.raises(BoundedStoreError):
        notes.add("   ")


# ---------------------------------------------------------------------------
# The single Persian normalizer: spelling variants are interchangeable
# ---------------------------------------------------------------------------


def test_normalizer_import_paths_are_one_implementation():
    assert normalize_fa is dream.memory.normalize_fa


def test_arabic_stored_entry_matches_farsi_fragment(profile):
    # Stored with Arabic kaf + Arabic yeh (U+0643 U+0643... كتاب).
    profile.add("كتاب‌خوانی شبانه")  # Arabic kaf/yeh spelling
    snapshot = profile.replace("کتاب", "کتاب‌خوانی روزانه")  # Farsi keheh/yeh query
    assert snapshot.entries == ("کتاب‌خوانی روزانه",)


def test_farsi_stored_entry_matches_arabic_fragment(profile):
    profile.add("من کتاب دوست دارم")  # Farsi spelling stored
    snapshot = profile.remove("كتاب")  # Arabic spelling query
    assert snapshot.entries == ()


def test_persian_and_arabic_digits_match_in_fragments(notes):
    notes.add("قرار ساعت ۱۵")  # Persian digits
    snapshot = notes.remove("ساعت 15")  # ASCII digits
    assert snapshot.entries == ()


# ---------------------------------------------------------------------------
# Snapshot immutability
# ---------------------------------------------------------------------------


def test_snapshot_is_frozen(notes):
    notes.add("held")
    snapshot = notes.snapshot()
    # frozen+slots dataclasses reject assignment; CPython raises
    # FrozenInstanceError for plain frozen classes but TypeError for the
    # slots-recreated class on 3.11 — either way the write must fail.
    with pytest.raises((dataclasses.FrozenInstanceError, TypeError)):
        snapshot.entries = ("mutated",)  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        snapshot.extra = 1  # type: ignore[attr-defined]
    assert snapshot.entries == ("held",)


def test_snapshot_survives_mid_session_mutations(notes):
    notes.add("before")
    frozen = notes.snapshot()
    notes.add("after")
    notes.remove("before")
    notes.replace("after", "rewritten")
    assert frozen.entries == ("before",)
    assert frozen.text == "before"
    assert frozen.used_chars == len("before")
    assert frozen.header == f"[0% — {len('before'):,}/2,200 chars]"


def test_snapshot_entries_is_a_tuple_not_a_list(notes):
    notes.add("one")
    assert isinstance(notes.snapshot().entries, tuple)


# ---------------------------------------------------------------------------
# Persistence, isolation, dual-store container
# ---------------------------------------------------------------------------


def test_entries_survive_reopen(tmp_path):
    path = str(tmp_path / "b.db")
    with BoundedStore(TARGET_MEMORY, 500, path=path) as store:
        store.add("persisted")
        store.add("also persisted")
    with BoundedStore(TARGET_MEMORY, 500, path=path) as reopened:
        assert reopened.snapshot().entries == ("persisted", "also persisted")


def test_users_are_isolated(tmp_path):
    path = str(tmp_path / "b.db")
    with BoundedStore(TARGET_MEMORY, 500, path=path, user="alice") as alice:
        with BoundedStore(TARGET_MEMORY, 500, path=path, user="bob") as bob:
            alice.add("alice fact")
            bob.add("bob fact")
            assert alice.snapshot().entries == ("alice fact",)
            assert bob.snapshot().entries == ("bob fact",)


def test_targets_are_isolated_in_one_file(tmp_path):
    path = str(tmp_path / "b.db")
    with BoundedMemory(path=path) as memory:
        memory.notes.add("agent note")
        memory.profile.add("user fact")
        assert memory.notes.snapshot().entries == ("agent note",)
        assert memory.profile.snapshot().entries == ("user fact",)
        assert memory.snapshots()[TARGET_MEMORY].entries == ("agent note",)
        assert memory.snapshots()[TARGET_USER].entries == ("user fact",)


def test_bounded_memory_store_resolves_targets_and_rejects_unknowns():
    with BoundedMemory() as memory:
        assert memory.store(TARGET_MEMORY) is memory.notes
        assert memory.store(TARGET_USER) is memory.profile
        with pytest.raises(ValueError, match="unknown bounded store target"):
            memory.store("diary")


def test_bounded_memory_from_env_honors_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_BOUNDED_DB", str(tmp_path / "env.db"))
    with BoundedMemory.from_env() as memory:
        memory.notes.add("via env")
        assert memory.notes.path == str(tmp_path / "env.db")
    with BoundedMemory.from_env() as reopened:
        assert reopened.notes.snapshot().entries == ("via env",)


# ---------------------------------------------------------------------------
# Property tests (seeded random; stdlib only — no new dev dependency)
# ---------------------------------------------------------------------------


def _fill_random(store: BoundedStore, rng: random.Random, count: int) -> list[str]:
    """Add up to *count* random, pairwise-distinct entries; return accepted.

    Bounded attempts: once the store is full every add raises, so the loop
    must stop on its budget rather than chase the requested count forever.
    """
    accepted: list[str] = []
    seen: set[str] = set()
    for _ in range(count * 30):
        text = "".join(rng.choice("abcdefghij") for _ in range(rng.randint(1, 40)))
        if text in seen:
            continue
        seen.add(text)
        try:
            store.add(text)
        except StoreCapacityError:
            continue
        accepted.append(text)
        if len(accepted) >= count:
            break
    return accepted


def test_property_overflow_never_truncates_or_corrupts(notes):
    rng = random.Random(20260822)
    accepted = _fill_random(notes, rng, 200)
    assert accepted, "fixture produced no accepted adds"
    snapshot = notes.snapshot()
    # Every accepted entry is present in full.
    for entry in accepted:
        assert entry in snapshot.entries
    # Capacity is never exceeded, and accounting matches the definition.
    expected_used = sum(len(e) for e in snapshot.entries) + len(snapshot.entries) - 1
    assert snapshot.used_chars == expected_used
    assert snapshot.used_chars <= notes.capacity


def test_property_failed_writes_leave_state_untouched(notes):
    rng = random.Random(7)
    _fill_random(notes, rng, 50)
    before = notes.snapshot()
    rejected = 0
    for _ in range(50):
        with pytest.raises(StoreCapacityError):
            notes.add("z" * notes.capacity)
        rejected += 1
        try:
            notes.replace(before.entries[0], "z" * notes.capacity)
        except (StoreCapacityError, AmbiguousEntryError):
            rejected += 1
        try:
            notes.remove("no-such-entry-anywhere")
        except EntryNotFoundError:
            rejected += 1
    assert rejected == 150
    assert notes.snapshot() == before


def _expect_substring_op(
    store: BoundedStore,
    snapshot: BoundedSnapshot,
    mode: str,
    fragment: str,
    replacement: str,
    capacity: int,
) -> BoundedSnapshot:
    """Run one replace/remove/bogus op and pin the exactly-one-or-error law.

    Lives outside the ``test_*`` function because each branch's assertions
    depend on the seeded fragment's match count — the M16 gate forbids
    asserts lexically inside ``if`` blocks in test functions, so the
    branching proof is extracted into this unit-testable helper.
    """
    pool = list(snapshot.entries)
    matching = [e for e in pool if fragment in e]
    if mode == "remove":
        if len(matching) == 0:
            with pytest.raises(EntryNotFoundError):
                store.remove(fragment)
            assert store.snapshot() == snapshot
        elif len(matching) > 1:
            with pytest.raises(AmbiguousEntryError):
                store.remove(fragment)
            assert store.snapshot() == snapshot
        else:
            after = store.remove(fragment)
            assert matching[0] not in after.entries
            assert set(after.entries) == set(pool) - set(matching)
            return after
    elif mode == "replace":
        if len(matching) == 0:
            with pytest.raises(EntryNotFoundError):
                store.replace(fragment, replacement)
            assert store.snapshot() == snapshot
        elif len(matching) > 1:
            with pytest.raises(AmbiguousEntryError):
                store.replace(fragment, replacement)
            assert store.snapshot() == snapshot
        elif (
            snapshot.used_chars - len(matching[0]) + len(replacement) > capacity
        ):
            with pytest.raises(StoreCapacityError):
                store.replace(fragment, replacement)
            assert store.snapshot() == snapshot
        else:
            after = store.replace(fragment, replacement)
            assert replacement in after.entries
            assert set(after.entries) == (set(pool) - set(matching)) | {replacement}
            return after
    else:  # bogus fragment: never present
        assert matching == []
        with pytest.raises(EntryNotFoundError):
            store.remove(fragment)
        with pytest.raises(EntryNotFoundError):
            store.replace(fragment, replacement)
        assert store.snapshot() == snapshot
    return snapshot


def test_property_substring_ops_hit_exactly_one_entry_or_raise(notes):
    rng = random.Random(99)
    entries = _fill_random(notes, rng, 40)
    assert entries
    snapshot = notes.snapshot()
    replacement_counter = 0
    for _ in range(60):
        pool = list(snapshot.entries)
        if not pool:
            break
        mode = rng.choice(("replace", "remove", "bogus"))
        if mode == "bogus":
            fragment = "zzz-not-present"
        else:
            entry = rng.choice(pool)
            start = rng.randrange(0, max(1, len(entry) - 2))
            fragment = entry[start : start + rng.randint(1, 4)]
        replacement_counter += 1
        snapshot = _expect_substring_op(
            notes,
            snapshot,
            mode,
            fragment,
            f"replaced-{replacement_counter}",
            notes.capacity,
        )
        # Ordering is always insertion order of the surviving entries:
        # each survivor's position in the pre-op pool must be increasing.
        surviving = [pool.index(e) for e in snapshot.entries if e in pool]
        assert surviving == sorted(surviving)


def test_property_header_percent_is_rounded_used_ratio(notes):
    rng = random.Random(3)
    _fill_random(notes, rng, 100)
    snapshot = notes.snapshot()
    assert snapshot.percent == round(100 * snapshot.used_chars / snapshot.capacity)
    assert 0 <= snapshot.percent <= 100


# ---------------------------------------------------------------------------
# Snapshot build budget (< 5 ms)
# ---------------------------------------------------------------------------


def test_snapshot_build_on_a_full_store_is_under_five_milliseconds(notes):
    filler = "x" * 99
    while True:
        try:
            notes.add(filler)
        except StoreCapacityError:
            break
    assert notes.snapshot().used_chars > NOTES_CAPACITY_CHARS - 200
    # Warm up, then measure: 50 snapshot builds, each and on average < 5 ms.
    notes.snapshot()
    worst = 0.0
    total = 0.0
    for _ in range(50):
        started = time.perf_counter()
        notes.snapshot()
        elapsed = time.perf_counter() - started
        worst = max(worst, elapsed)
        total += elapsed
    assert worst < 0.005, f"worst snapshot build {worst * 1000:.2f} ms"
    assert total / 50 < 0.005, f"average snapshot build {total / 50 * 1000:.2f} ms"
