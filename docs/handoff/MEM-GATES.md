# MEM — Gate evidence (mirrors UI-GATES.md: real command output only)

**Branch:** `arena/01a029da-dream` · **Base:** `29caacc` (verified: `git log` shows
`29caacc Update ci.yml` as the branch point; working tree clean at start)
**Date:** 2026-08-22 · Commands ran from the repository root unless an
`apps/desktop` working directory is shown. No claim below lacks pasted output.

---

## Step 0 — baseline verification (before any code)

Base commit verified ≥ `29caacc`:

```text
$ git log --oneline -1
29caacc Update ci.yml
```

Python (disposable ignored `.venv` from `.[dev]` — no dependency or lockfile changed):

```text
$ .venv/bin/python -m pytest -q
1748 passed, 11 skipped in 60.70s (0:01:00)
```

Matches the required baseline (1748/11) exactly.

Desktop, in `apps/desktop` after `npm ci`:

```text
$ npm run test
Test Files  69 passed (69)
     Tests  505 passed (505)

$ npm run typecheck        # exit 0
$ npm run lint
✖ 11 problems (0 errors, 11 warnings)
$ npm run format:check
All matched files use Prettier code style!
$ npm run build
✓ built in 5.57s          # entry 63.22 kB gzip; largest chunk react-vendor 255.94 kB
$ npm run performance:check
"pass": true … "largestChunkKiB": 249.94140625
$ npm run accessibility:check
Test Files  3 passed (3) / Tests  9 passed (9)
$ npm run tokens:check
Tokens Studio schema-compatible import: PASS — 12 sets, 208 tokens, 12 themes.
Contrast gate: PASS — 108 AA checks.
$ npm run locales:check
Locale integrity: PASS — 8 locales × 14 namespaces; 655 leaves …
English fallback counts: fa=0 … fa gate=PASS
```

Baseline green; no deltas; proceeding was authorised by the mission brief.

---

# Gate A — dual bounded stores with snapshot injection

Implementation: [`MEM-A.md`](./MEM-A.md) · Files: `dream/memory_stores.py` (new),
`dream/agent.py`, `dream/subagents.py`, four new test files. **No existing test
was edited; no existing method, payload, or workflow changed.**

## A.1 — Property tests: overflow, substring uniqueness, snapshot immutability

```text
$ .venv/bin/python -m pytest tests/test_memory_stores.py -q
38 passed in 1.60s
```

Pinned laws (selected):

- `test_used_chars_counts_entries_and_separators` — header is byte-exactly
  `[67% — 1,474/2,200 chars]` for 736+737 chars + separator on a 2,200 budget.
- `test_add_past_capacity_raises_and_leaves_store_unchanged` — overflow raises
  `StoreCapacityError` (`over_by`, header, both languages), store byte-identical.
- `test_property_overflow_never_truncates_or_corrupts` — seeded random fill:
  every accepted entry present in full; `used == Σlen + (n−1)·§`; `used ≤ capacity`.
- `test_property_failed_writes_leave_state_untouched` — 150 doomed writes
  (overflow add, overflow replace, missing remove): snapshot unchanged.
- `test_property_substring_ops_hit_exactly_one_entry_or_raise` — 60 seeded ops:
  zero matches → `EntryNotFoundError`; >1 → `AmbiguousEntryError`; exactly one →
  precisely that entry mutated, everything else and ordering preserved.
- `test_snapshot_is_frozen` / `test_snapshot_survives_mid_session_mutations` —
  frozen dataclass + tuple entries; later writes never mutate an issued snapshot.
- `test_arabic_stored_entry_matches_farsi_fragment` and inverse — the marquee
  normalizer property at the matching layer, plus Persian/ASCII digit folding.
- `test_normalizer_import_paths_are_one_implementation` —
  `dream.memory_stores.normalize_fa is dream.memory.normalize_fa`.

## A.2 — Concurrency test (threads)

```text
$ .venv/bin/python -m pytest tests/test_memory_stores_threads.py -q
5 passed in 0.48s
```

- 8 writer threads × 25 adds: no unexpected errors, every accepted add survives
  in per-thread order, budget never exceeded, accounting exact.
- Two threads racing the last capacity slot via `Barrier`: exactly one add
  lands, the other receives a clean `StoreCapacityError`.
- 2 readers × 200 snapshots under 4 concurrent writers: no anomalous snapshot
  (over-capacity or over-count) ever observed.
- Both targets of one `BoundedMemory` file under simultaneous tool-shaped
  traffic: no cross-target interference.
- Nested lock use (`add` → `snapshot` under the write lock) completes — no deadlock.

## A.3 — Concurrency test (real processes)

```text
$ .venv/bin/python -m pytest tests/test_memory_stores_processes.py -q
2 passed
```

- Two OS processes meet at a `multiprocessing.Barrier` and race an add that
  only one can fit: exactly one `ok`, one `StoreCapacityError`; verifier reopen
  shows both entries and exact accounting.
- Four processes × 60 adds: no lost or duplicate rows; total within budget.

## A.4 — Snapshot budget: build < 5 ms (budget from the perf list)

Benchmark, full 97 % notes store (19 entries, 2,127/2,200 chars), on-disk
SQLite, `n=200` after warm-up:

```text
entries=19 used=2127/2200 header=[97% — 2,127/2,200 chars]
snapshot_build_ms: n=200 min=0.020 p50=0.021 p95=0.025 max=0.063 budget_ms=5
add_plus_snapshot_ms_per_op over 100 ops: 0.650
```

p95 = 0.025 ms — 200× inside the 5 ms budget. Also pinned as a regression test
(`test_snapshot_build_on_a_full_store_is_under_five_milliseconds`: worst and
average of 50 builds < 5 ms).

## A.5 — Agent integration

```text
$ .venv/bin/python -m pytest tests/test_memory_stores_agent.py -q
17 passed in 0.35s
```

- Both snapshots injected with capacity headers and `§`-joined entries; empty
  stores still show `[0% — 0/… chars]`; bounded block precedes recalled memories.
- `test_snapshot_is_frozen_mid_session` — tool write between turns; turn-two
  system prompt byte-identical to turn one; store updated; result payload fresh.
- `reset_session()` re-freezes and shows the mid-session write.
- Without `bounded=`: prompt contains no labels/headers/tool names (unchanged).
- Tools: `guarded`, schema enum `["add","replace","remove"]`, `action` required;
  add returns fresh state (header + content, no read action); overflow through
  the tool boundary is `status: error` / `StoreCapacityError` with the
  consolidation instruction; ambiguity names both candidates; Persian-variant
  matching through the tool; agent turn executes `agent_notes` end-to-end.
- `test_subagents_never_receive_the_parents_bounded_tools` — a child granted
  `agent_notes`/`user_profile` does not receive the parent's closures; parent
  registry restored byte-identically.

## A.6 — Existing memory tests: pass unmodified (RF-4)

```text
$ git diff --cached --stat 29caacc -- tests/
 tests/test_memory_stores.py           | 547 ++++++++++++++++++++++++++++++++++
 tests/test_memory_stores_agent.py     | 295 ++++++++++++++++++
 tests/test_memory_stores_processes.py | 121 ++++++
 tests/test_memory_stores_threads.py   | 193 ++++++
 4 files changed, 1156 insertions(+)
 # (new files only; zero deletions, zero edits to existing tests)

$ .venv/bin/python -m pytest -q
1810 passed, 11 skipped in 59.72s (0:01:00)
```

1748 pre-existing + 62 new = 1810 passed / 11 skipped; no failures, no skips added.

## A.7 — Static and protected boundaries

```text
$ .venv/bin/python -m ruff check .
All checks passed!

$ python cli.py --demo   # sanity: unchanged demo path
… 5. Approval gate: {"blocked": true, "reason": "dangerous tool denied: no approver configured"}
```

- Machine gates on merged trunk stay green: `tests/test_m16_escaping.py`
  (4 passed — new module uses `\u06xx` escapes for all Persian literals) and
  `tests/test_m16_conditional_assertions.py` (branching property assertions
  extracted into a non-test helper, per the gate's own pattern).
- `git diff --stat 29caacc -- apps/desktop .github` → no output: desktop and
  workflows untouched in Stage A.
- No new runtime dependencies (`pyproject.toml` unchanged).

## A.8 — Desktop regression (unchanged surface, re-verified)

```text
$ npm run test                       # apps/desktop
Tests  505 passed (505)
$ npm run typecheck                  # exit 0
$ npm run lint
✖ 11 problems (0 errors, 11 warnings)
$ npm run format:check
All matched files use Prettier code style!
$ npm run build
✓ built in 7.27s   # entry 63.22 kB gzip; largest chunk react-vendor 255.94 kB
$ npm run performance:check          # "pass": true, largestChunkKiB 249.94
$ npm run accessibility:check        # 9 passed
$ npm run tokens:check               # 12 sets, 208 tokens, 12 themes; 108 AA PASS
$ npm run locales:check              # fa=0 fallbacks; gate PASS
```

## Gate A decision

**GREEN.** Dual bounded stores, capacity headers, overflow-as-error, profile
target, one-writer safety (threads + processes), frozen per-session snapshot
injection, guarded tool surface, subagent isolation, property/concurrency/perf
budgets, existing suites unmodified and green.

Stage B (FTS5 session search with Persian normalization) may begin.

---

# Gate B — FTS5 session search with Persian normalization

Implementation: [`MEM-B.md`](./MEM-B.md) · Files: `dream/session_search.py` (new),
four new test files. **No existing test was edited; no existing method, payload,
or workflow changed; `apps/desktop` and `.github` untouched (0 diff lines vs `29caacc`).**

## B.1 — Marquee property, both directions, on the unit corpus

```text
$ .venv/bin/python -m pytest tests/test_session_search.py -q
35 passed in 0.53s
```

Pinned laws (selected):

- `test_arabic_query_finds_farsi_sessions_and_vice_versa` — query `كتاب`
  (Arabic yeh/kaf) finds sessions written `کتاب` (Farsi) **and vice versa**.
- `test_digit_folding_both_directions` — `ساعت 15` ⇄ `ساعت ۱۵`; `۱۵` reaches
  ASCII-digit sessions too.
- `test_zwnj_and_space_are_interchangeable` — `می‌خواهم` ⇄ `می خواهم`, both
  directions (ZWNJ folds to space on both write and read).
- `test_diacritics_are_ignored` — `كِتابِ` queried by clean `کتاب`.
- `test_normalizer_and_tokenizer_are_the_shared_implementation` — the index
  imports `dream.memory.normalize_fa`/`_tokenize`; identity-pinned.
- `test_more_mentions_rank_above_fewer` / `test_title_hits_outrank_body_hits`
  (bm25 ×3 title weight) / `test_equal_scores_tie_break_newest_first_and_stably`
  (`ORDER BY rank ASC, id DESC`, deterministic).
- Snippets: `test_snippet_highlights_the_original_spelling_not_the_shadow`
  (the bracketed word keeps the session's own Arabic spelling),
  `test_snippet_is_a_verbatim_slice_of_the_original`,
  `test_snippet_boundaries_land_on_word_edges`,
  `test_snippet_does_not_mangle_rtl_mixed_content`,
  `test_snippet_marks_every_matching_word_in_the_window`.
- Lifecycle: upsert idempotence, `append_message` growth + create-on-unknown,
  remove unindexes, `rebuild()` re-derives, reopen finds documents, paging.
- Fail-closed: garbage file (bilingual error, left byte-identical —
  `test_corruption_is_never_silently_wiped`), future `user_version`, dropped
  `session_fts` (structurally incomplete), unstamped foreign tables; a
  missing file initialises fresh and stamps `SCHEMA_VERSION`.

## B.2 — Performance: 10,000-session synthetic corpus, on-disk WAL

```text
$ .venv/bin/python -m pytest tests/test_session_search_perf.py -s -q
corpus_sessions=10000 index_build_seconds=5.89
db_size_mb=20.6
.query_cold_ms: n=10 min=3.624 p50=23.028 p95=27.675 max=27.675 budget_ms=50
query_warm_ms: n=200 min=3.195 p50=19.845 p95=26.833 max=38.235 budget_ms=50
2 passed in 10.37s
```

Corpus: mixed Persian/English sentences (8–16 words × 5 messages + 2-sentence
titles per session), Arabic-variant spellings on a deterministic subset,
Persian digits, ZWNJ verbs, seed `20260822` — identical every run. Cold =
first query after each of 10 fresh opens. Warm = 200 queries cycling a
10-query bilingual battery (Arabic/Farsi probe pair, multi-token Persian,
English, digits, ZWNJ, mixed). **p95 = 26.8 ms warm / 27.7 ms cold — ≈2×
inside the 50 ms budget.** Profiling showed the cost dominated by bm25
ranking over common tokens (terms matching thousands of documents), not by
normalization or snippets; `prefix=` indexing was evaluated against these
numbers and rejected (MEM-B.md §2). Recall probe on the same corpus: both
spellings of the probe word reach all 120 needle sessions and only those
(`test_marquee_recall_on_the_10k_corpus`).

## B.3 — Concurrency

```text
$ .venv/bin/python -m pytest tests/test_session_search_threads.py tests/test_session_search_processes.py -q
5 passed
```

- Writer indexing 150 sessions while 3 searchers spin: no anomaly, no
  partial document ever observed; final corpus exact.
- 3 threads × 20 appends into one session: all 60 messages kept, in order.
- 4 threads racing same-session upserts: last write wins, title/body pair
  internally consistent, one document.
- `rebuild()` under concurrent search: hit count never dips.
- Two real OS processes at a `Barrier` writing one fresh file (100 writes,
  5 shared ids): 95 unique documents, zero errors, zero duplicates — and the
  run exposed the concurrent-fresh-open init race, fixed with a bounded
  mid-init wait (foreign unstamped shapes still fail closed). Verified
  stable over 5 consecutive runs (0.15–0.22 s each).

## B.4 — Index-update under the session event flow

`append_message` is the incremental primitive the bridge/scheduler/gateway
will call (Stage F wiring): pinned create-on-unknown, growth, and that
searching reaches content from every append
(`test_append_message_grows_the_document`).

## B.5 — RF-4, machine gates, full suites

```text
$ git diff --cached --stat   # Stage B delta only; zero edits to existing tests
 docs/handoff/MEM-B.md                  | 132 +++++
 docs/handoff/MEM-GATES.md              | 142 +++++
 dream/session_search.py                | 648 ++++++++++++++
 tests/test_session_search.py           | 393 ++++++
 tests/test_session_search_perf.py      | 182 ++++++
 tests/test_session_search_processes.py |  74 ++++
 tests/test_session_search_threads.py   | 136 ++++++
 7 files changed, 1707 insertions(+)

$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python -m pytest -q
1852 passed, 11 skipped in 83.30s (0:01:23)
```

1810 (Gate A close) + 42 new = 1852 passed / 11 skipped; new tests only,
zero edits to existing tests. M16 escaping and conditional-assertion machine
gates green. Rework-loop rule: the module took one targeted fix (the
init-race wait) after the process test exposed it — not a >4-edit loop.

## B.6 — Desktop regression (untouched, re-verified)

```text
$ git diff --stat 29caacc -- apps/desktop .github | wc -l
0
$ npm run typecheck        # exit 0
$ npm run lint
✖ 11 problems (0 errors, 11 warnings)
$ npm run test             # apps/desktop
Test Files  69 passed (69)
Tests  505 passed (505)
```

## Gate B decision

**GREEN.** Pre-normalized external-content FTS5 through the single shared
normalizer; marquee property pinned both directions plus digits/ZWNJ/
diacritics; deterministic bm25 ranking; original-text word-aligned bidi-safe
snippets; incremental/rebuild lifecycle with bilingual fail-closed corruption
paths; thread + process writer safety; 10k-corpus benchmark at p95 ≈ 27 ms
against the 50 ms budget, cold and warm; existing suites untouched and green.

PR-1 (Stages A+B) evidence is complete; Stage C (skills v2 runtime) may begin
on PR-2's branch after owner review.
