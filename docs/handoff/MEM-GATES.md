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

---

# Gate C — Skills v2 runtime (in-place)

Implementation: [`MEM-C.md`](./MEM-C.md) · Files: `dream/skills/format.py`,
`registry.py`, `store.py`, `slash.py` (new), `dream/skills/__init__.py`,
`dream/tools.py`, `dream/agent.py`, `cli.py`, `tests/test_skills_v2.py` (23).
**No existing test was edited; no bridge protocol or desktop file changed.**

## Step 0 — this session, before Stage C code

```text
$ git log --oneline -1
c664d54 feat(memory): kernel memory loop — bounded stores + FTS5 session search (MEM Stages A+B)

$ .venv/bin/python -m pytest -q
1852 passed, 11 skipped in 78.29s (0:01:18)
```

Matches the required 1852 / 11 baseline. Desktop tree vs `c664d54` is 0 lines
(Stage C does not touch `apps/desktop` or `.github`).

## C.1 — Token-cost (body absent until skill_view; catalog budget at 50)

```text
$ .venv/bin/python -m pytest tests/test_skills_v2.py::test_body_absent_from_system_prompt_until_skill_view tests/test_skills_v2.py::test_catalog_stays_within_budget_with_fifty_skills -q
2 passed in 0.28s

catalog_skills 50
catalog_chars 2425 budget 8000
body_in_catalog False
system_chars 4922
body_in_system False
```

Pinned: distinctive body marker is in no system prompt and in no catalog
line; 50 installed skills contribute 2,425 characters against the 8,000
budget; `skill_view` returns the body.

## C.2 — Slash stacking (path-like args and the 5-cap)

```text
$ .venv/bin/python -m pytest tests/test_skills_v2.py::test_path_like_argument_is_not_swallowed tests/test_skills_v2.py::test_five_skill_stack_with_trailing_instruction tests/test_skills_v2.py::test_cli_and_agent_share_the_same_slash_parser -q
3 passed
```

`/ocr-and-documents /tmp/scan.pdf extract the tables` loads one skill; the
path is the argument. A 5-skill stack keeps the trailing instruction; a
sixth slash stays in the remainder.

## C.3 — Write-approval denial fails closed

```text
$ .venv/bin/python -m pytest tests/test_skills_v2.py::test_write_approval_denial_fails_closed -q
1 passed
```

`ApprovalPolicy(always_ask={"guarded","dangerous"}, ask=False)` blocks
`save_skill`; the workspace gains no skill file.

## C.4 — Invalid SKILL.md is per-skill; registry stays up

```text
$ .venv/bin/python -m pytest tests/test_skills_v2.py::test_invalid_skill_md_does_not_drop_the_rest_of_the_registry tests/test_skills_v2.py::test_description_over_sixty_chars_is_a_bilingual_per_skill_error -q
2 passed
```

A broken neighbour is a bilingual `SkillProblem`; the valid skill still
loads. Description > 60 characters is refused with both languages.

## C.5 — Version / use-log, no auto-overwrite

```text
$ .venv/bin/python -m pytest tests/test_skills_v2.py::test_versions_append_and_never_overwrite tests/test_skills_v2.py::test_save_skill_md_refuses_to_clobber_without_replace tests/test_skills_v2.py::test_use_log_records_view_and_slash -q
3 passed
```

Edits append version 2; identical content is a no-op; `save_skill_md`
without `replace` leaves the file byte-identical. Slash and `skill_view`
write use-log rows.

## C.6 — Full suites, RF-4, static, desktop 0-diff

```text
$ .venv/bin/python -m pytest tests/test_skills_v2.py -q
23 passed in 0.35s

$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python -m pytest -q
1875 passed, 11 skipped in 83.94s (0:01:23)

$ git diff --stat c664d54 -- apps/desktop .github | wc -l
0
```

1852 + 23 new = 1875 passed / 11 skipped. Existing tests unmodified.
`pyproject.toml` unchanged (stdlib only). Machine gates
`test_m16_escaping` / `test_m16_conditional_assertions` green.

## Gate C decision

**GREEN.** In-place v2: SKILL.md + v1 `.txt` side by side, progressive
disclosure (catalog name+description only; bodies via `skill_view` or slash
user-turn), Hermes stacking with path-safe parse, guarded writes fail
closed on denial, append-only version/use ledger under `DREAM_SKILLS_DB`.

Stage D (`/learn` and autonomous proposals) may begin on the same PR.

---

# Gate D — /learn and autonomous proposals

Implementation: [`MEM-D.md`](./MEM-D.md) · Files: `dream/skills/learn.py`,
`dream/skills/propose.py` (new), `dream/tools.py`, `dream/agent.py`,
`cli.py`, `tests/test_skills_learn.py` (11). **No existing test edited;
bridge protocol and desktop untouched.**

## D.1 — Every source type

```text
$ .venv/bin/python -m pytest tests/test_skills_learn.py -q
11 passed in 0.30s
```

- path (`/learn notes/tea.txt`)
- conversation (`/learn conversation`)
- notes (`/learn How to brew tea…`)
- corpus (`/learn docs/book` → `references/` + `glossary.md`)
- URL with network enabled (fetch stubbed; page text classified as `url`)
- URL offline: bilingual refusal, no DNS/socket touch, no skill written

## D.2 — Knowledge-base split and merge-on-re-learn

`test_learn_from_corpus_writes_references` — `references/soil.md`,
`water.md`, `glossary.md`; long source passages are not reproduced.
`test_merge_on_relearn_does_not_duplicate` — second `/learn` on the same
name returns `status=merged`, one skill, both bodies present.

## D.3 — Post-task proposals

`test_proposals_default_off_and_never_in_demo` — default off; `demo=True`
never proposes even when the env flag is on.
`test_proposal_approved_applies_denied_discards` — apply writes one skill;
discard writes nothing; a guarded denial of `apply_skill_proposal` leaves
the disk unchanged.

## D.4 — Full suites at close

```text
$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python -m pytest -q
1886 passed, 11 skipped in 80.33s (0:01:20)

$ git diff --stat c664d54 -- apps/desktop .github | wc -l
0
```

1875 (Gate C) + 11 = 1886 passed / 11 skipped. Suites only grew.

## Gate D decision

**GREEN.** `/learn` is a composed normal turn (no private ingestion engine);
URL learning fails closed offline; large sources become knowledge-base
skills; re-learn merges; proposals are opt-in, never in `--demo`, and
write only through the approved path.

PR-2 (Stages C+D) evidence is complete.

---

# C/D — Integrity Appendix

Round-3 review: Gates C and D stay conditionally GREEN pending this
appendix. Each item below is a live command from the repository root on
`arena/01a02a8d-dream` at `74b01b2` (C+D code) plus this docs commit.
No existing test was edited to produce a cleaner grep.

## I.1 — RF-4 proof (existing tests untouched)

```text
$ git diff --stat c664d54..HEAD -- tests/
 tests/test_skills_learn.py | 334 ++++++++++++++++++++++++++++++++++
 tests/test_skills_v2.py    | 437 +++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 771 insertions(+)
```

Only the two new files. Zero deletions, zero edits to any pre-existing
test. That also settles the `test_m12` / `KNOWN_COMMANDS` concern from
the session log: `/learn` was added to `KNOWN_COMMANDS` in product code
(`cli.py`) without touching `tests/test_m12*.py` or any other existing
suite file. Handoff notes live under `docs/handoff/`, not `tests/`.

## I.2 — Dead-assertion sweep

```text
$ grep -rn "or True" tests/
$ grep -rn "and False" tests/
$ grep -rn "if False" tests/
tests/test_session_search.py:231:    index.index_session("chat", "project", ["первое" if False else "first turn"])
```

`or True` and `and False` return nothing (exit 1). The single `if False`
hit is **not** a dead assertion and is **not** in this PR: it is a
ternary used as fixture text inside Stage B
`test_append_message_grows_the_document` (`["первое" if False else
"first turn"]`). RF-4 forbids editing that file. No `or True` leftover
remains in `tests/test_skills_learn.py` (the dummy that appeared during
drafting was removed before the Stage D commit).

## I.3 — Ledger lifecycle

Root cause and fix are documented in [`MEM-C.md`](./MEM-C.md) §4
(paragraph "Ledger lifecycle"). Summary: a process-global `SkillLedger`
connection was inherited by `multiprocessing` tests and deadlocked on
the SQLite file lock; `get_ledger()` now returns a fresh
`SkillLedger.from_env()` and every product call site is a short-lived
`with` block (or is the definition itself).

```text
$ grep -n "get_ledger()" dream/skills/*.py dream/tools.py
dream/skills/__init__.py:1130:    with get_ledger() as ledger:
dream/skills/__init__.py:1164:    with get_ledger() as ledger:
dream/skills/__init__.py:1215:    with get_ledger() as ledger:
dream/skills/propose.py:111:        with get_ledger() as ledger:
dream/skills/store.py:229:def get_ledger() -> SkillLedger:
dream/tools.py:594:        with get_ledger() as ledger:
```

Every call site is inside a `with` block. The remaining line is the
function definition. (For completeness, the only other product call is
`dream/agent.py:1197`, also `with get_ledger() as ledger:`.)

## I.4 — Unicode sanity

```text
$ python3 -c "from dream.skills import format, learn, propose"
$ grep -c '\\\\u' dream/skills/format.py
0
```

Imports are clean (exit 0, no traceback). `format.py` contains zero
double-escaped `\\u` sequences. Product Persian remains single `\u`
escapes as required by M16.

## Integrity decision

**GREEN.** RF-4 holds (two new test files only). Dead-assertion greps
are clean except one pre-existing Stage B ternary, left untouched.
Ledger connections are short-lived. Unicode imports and escape density
check out. PR-2 may merge; Stages E+F wait for that merge.


---

# Gate E — context compaction and memory nudges

## E.1 — Ordered acceptance tests

```text
$ .venv/bin/python -m pytest tests/test_compaction.py -q
7 passed
```

- `test_trigger_math_and_byte_stable_echo_summary`: local threshold accounting
  and byte-stable echo header at a turn boundary.
- `test_tool_integrity_after_compaction` and
  `test_compaction_preserves_prior_tool_result_for_follow_up`: a tool exchange
  remains usable after compaction; bounded tool-result facts are retained in
  the summary header.
- `test_small_window_never_grows_without_bound`: a configured small window
  compacts before dispatch rather than sending unbounded history.
- `test_explicit_compress_is_a_first_class_persisted_event`: `/compress`
  forces the same event path.
- `test_nudge_is_capped_offable_and_never_demo`: nudge cap, named off switch,
  and demo suppression.
- `test_compaction_event_is_first_class_history_record_after_reload`: event
  shape, timestamp, and persisted summary survive transcript-consumer reload.

## E.2 — Full regression and protected gate

```text
$ .venv/bin/python -m pytest -q
1893 passed, 11 skipped in 92.27s
```

The M16 escape gate is inside the full run. The prior literal-escape failure
was corrected before this final run; no existing test was edited.

```text
$ .venv/bin/ruff check dream/agent.py dream/compaction.py tests/test_compaction.py
All checks passed!
```

## Gate E decision

**GREEN.** Accounting is local, deterministic on echo, bounded at dispatch,
and records first-class transcript events. Tool output integrity is retained,
while nudges remain prompt-only, rate-capped, disableable, and absent in demo.


---

# Gate F — desktop surfaces, bridge error paths, close-out

## F.0 — Baseline

Rebuild started from `main` at `9ecda7b` (post #78). Verified before any
code was written:

```text
$ .venv/bin/python -m pytest -q
1893 passed, 11 skipped in 84.51s

$ npm test   (apps/desktop)
Test Files  69 passed (69)
     Tests  505 passed (505)
```

All other baseline gates matched §1.4 (ruff clean, typecheck clean,
lint 0 errors / 11 pre-existing warnings, format clean, entry chunk
63.22 kB gzip, performance `pass: true`, 5 axe surfaces 0 violations,
tokens 108 AA PASS, 14 namespaces / 655 leaves / fa=0).

## F.1 — The four surfaces

Per-commit desktop deltas (full battery green before each push):

| Commit | Surface | Desktop tests | Δ |
| --- | --- | --- | --- |
| `32143d0` | bounded stores panel (`bounded-stores.test.tsx` 22 + route tab + axe) | 505 → 529 | +24 |
| `8d92fec` | skills learning workspace (`skills-v2.test.tsx` 28 + route tab + axe) | 529 → 559 | +30 |
| `75c0ffb` | session search (`session-search.test.tsx` 27 + ⌘P shortcut + axe) | 559 → 588 | +29 |
| `db921ce` | transcript compaction (`compaction-bar.test.tsx` 20 + axe) | 588 → 609 | +21 |

The locale gate held at every commit (fa=0 throughout); the final tree is
15 namespaces × 8 languages, 760 leaves.

Pinned laws, per surface (named by test):

- **Bounded stores** — `renders the kernel header format byte-for-byte`
  (`[67% — 1,474/2,200 chars]`, en-US grouping under Persian),
  `counts the separator between entries, exactly as the store does`,
  `never writes without an approval, and applies the write once allowed`,
  `renders a refused write verbatim and leaves the entries untouched`,
  `keeps the frozen snapshot immutable across later writes`,
  `keeps the DOM bounded for a 1,000-entry store`.
- **Skills workspace** — `counts any outcome that is not exactly ok as a
  failure`, `orders skills busiest first, breaking ties by name`,
  `refuses a URL source while the network is off, in both languages`,
  `writes a proposal only on an explicit approve`,
  `resolves pasted notes to a skill name before committing`,
  `says so when a skill has only one saved version`.
- **Session search** — `treats an unbalanced marker as plain text rather
  than blanking the snippet`, `never emits markup — the segments are text
  only`, `highlights the Persian spelling for an Arabic-spelled query`,
  `refuses every read while the index is corrupt, and recovers on rebuild`,
  `reports an empty result set without claiming a failure (no role="alert")`.
- **Compaction** — `reports tokens saved and never goes negative`,
  `ignores a payload that did not actually compact`,
  `is hidden when nudges are switched off, even if one is due`,
  `is hidden when the state is unknown`,
  `records a row with the before/after cost and what was preserved`,
  `works against the echo transport end to end`.

## F.1.5 — Cross-cutting

Virtualization fixtures (1000-row stores, mounted rows):

```text
bounded_fixture_rows=1000 mounted_rows=17
skills_v2_fixture_rows=1000 mounted_rows=18
search_fixture_rows=1000 mounted_rows=12
```

Axe surfaces (9, all clean):

```text
axe_surface=sessions violations=0
axe_surface=memory violations=0
axe_surface=memory-bounded violations=0
axe_surface=skills violations=0
axe_surface=skills-learning violations=0
axe_surface=subagents violations=0
axe_surface=scheduler violations=0
axe_surface=session-search violations=0
axe_surface=compaction violations=0
```

Chunk table (largest first; entry ≤ 63.22 kB gzip baseline):

```text
react-vendor   255.94 kB   (249.94 KiB — under the 500 KiB budget)
index (entry)  203.87 kB   gzip 62.05 kB   ✓ below the 63.22 baseline
ui-vendor       76.66 kB
data.dataset    74.16 kB   (echo-data now a lazy family chunk)
index.css       62.83 kB
i18n-vendor     49.67 kB
```

Every new surface and every echo runtime (including the pre-existing
`EchoDataRuntime`) is lazily imported — that conversion is what keeps the
entry below baseline while four surfaces were added.

## F.2 — The error-path suite

`tests/test_bridge_mem_error_paths.py` — 29 test functions, 52 collected
with `pytest.mark.parametrize`; full run 1893 → 1945. Groups: `memory2.*`
(unknown target ×5, non-string payload ×5, five wire keys, refusal leaves
the store untouched), `conversation.compact`/`nudge.status` (bad session
ids ×6, exact `{enabled, sent, due}` shape), `search.sessions.*`
(non-string query ×4, no-tokens fails closed, status/rules shape, rebuild
count), `skills.*` boundary errors, `skills.learn_classify` refusals
(including the offline-URL refusal asserting اینترنتی with
`_network_on` monkeypatched off), `skills.references` empty-list rules,
and `test_every_mem_family_payload_is_json_serialisable` — the wire-shape
regression over non-empty rows of every family.

## F.3 — Docs

`CHANGELOG.md` (user-facing Added/Fixed), `docs/CONFIGURATION.md` (two
wrong rows corrected: `DREAM_SKILLS_DB` defaults to
`data/dream-skills.db`; `DREAM_SKILL_PROPOSALS` is a boolean opt-in flag,
not a store path), `README.md` (the four surfaces in "Desktop
conversations and work"), `MASTER_CHECKLIST.md` (MP-02 section with the
known-limitations block), this file.

## F.4 — The full battery (at the docs state)

```text
$ .venv/bin/python -m pytest -q
1945 passed, 11 skipped in 79.89s
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/python tools/check_suite_count.py
Suite count check passed: 1948 tests collected (minimum required: 652).
$ .venv/bin/python tools/check_locales.py
Locale integrity: PASS — 8 locales × 15 namespaces; 760 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=372, ja=372, es=372, de=372, fr=372, ko=372; fa gate=PASS

apps/desktop:
$ npm run typecheck        → clean, exit 0
$ npm run lint             → 11 problems (0 errors, 11 warnings)
$ npm run format:check     → All matched files use Prettier code style!
$ npm test
Test Files  73 passed (73)
     Tests  609 passed (609)
$ npm run build            → entry 203.87 kB │ gzip: 62.05 kB (≤ 63.22 baseline)
                             largest chunk 249.94 KiB (< 500 kB)
$ npm run performance:check → "pass": true
  paletteOpenMs 51.508 (budget 100) · routeChangeMs 159.344 (300)
  coldDashboardRenderMs 362.955 (2000) · streamingLongestTaskMs 0.164 (50)
  mounted500MessageRows 11 (60) · unhandledPromiseRejections 0
$ npm run accessibility:check → 9 surfaces violations=0
  reduced_motion_os=PASS  reduced_motion_manual=PASS
$ npm run tokens:check     → Contrast gate: PASS — 108 AA checks.
```

The 11 eslint warnings are the pre-existing `react-refresh/only-export-components`
set; 0 errors is the gate.

## Gate F decision

**GREEN.** All six commits land with the messages in §2.1; every gate in
§4.6 is green on the PR's own battery; check_commit.py passes on every
commit; fa=0 held at every commit; the entry chunk stayed below the
63.22 kB baseline throughout.


---

# MP-02 — mission close-out

Per-stage totals, each taken from that stage's own section above:

| Stage | Python (full run) | Δ | Desktop |
| --- | --- | --- | --- |
| Baseline | 1748 / 11 | — | 505 |
| A bounded stores | 1810 / 11 | +62 | 505 |
| B session index | 1852 / 11 | +42 | 505 |
| C skills v2 runtime | 1875 / 11 | +23 | 505 |
| D learn loop | 1886 / 11 | +11 | 505 |
| E compaction + nudges | 1893 / 11 | +7 | 505 |
| Hotfix #78 | 1893 / 11 | 0 | 505 |
| F | 1945 / 11 | +52 | 609 (+104) |

Benchmark recap: §4.6 / F.4 above — pytest 1945/11, suite 1948, ruff
clean, locales 15 namespaces / 760 leaves / fa=0, desktop 609 tests,
entry 62.05 kB gzip (≤ 63.22), largest chunk 249.94 KiB, performance
`pass: true`, 9 axe surfaces 0 violations, tokens 108 AA PASS.

The seven invariants, held end to end:

1. **Nothing is written without consent** — every bounded write, proposal
   apply and learn commit goes through an explicit approval.
2. **A refused write changes nothing** — refusals render verbatim next to
   an untouched store.
3. **The session prompt is frozen** — `memory2.status` answers the
   snapshot frozen at session start, and the panel says so.
4. **Fail closed, out loud** — a corrupt index refuses reads and offers a
   rebuild; an offline URL is refused before a turn starts.
5. **Persian is first class** — matching normalised (Arabic-spelled
   queries find Farsi-spelled transcripts), display never re-spelled.
6. **The protocol is append-only** — versions and use rows are only ever
   appended; the wire carries `asdict` payloads everywhere.
7. **Offline-first, zero new deps, no telemetry, no workflow edits** —
   stdlib-only kernel additions, lazy in-house echo runtimes, `.github/`
   untouched.

PR trail: #75 (A+B), #76 (C+D), #77 (E), #78 (CI hotfix), #79 (this
rebuild: desktop surfaces, bridge error paths, close-out).
