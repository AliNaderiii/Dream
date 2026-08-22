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
