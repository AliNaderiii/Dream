# MEM-B — Stage B: FTS5 session search with Persian normalization

**Date:** 2026-08-22
**Branch:** `arena/01a029da-dream` (on top of Gate-A commit `ec1cf9b`)
**Scope:** PR-1 (kernel memory), second half. Gate evidence: [`MEM-GATES.md`](./MEM-GATES.md) §Gate B.
**Owner architect:** MNEMOSYNE · **Implementation:** SA-1 IRINI (index/ranking) with SA-5 VERITAS (tests, races, perf)

## What was built

| Piece | File | Notes |
| --- | --- | --- |
| Search kernel | `dream/session_search.py` | `SessionSearchIndex` (external-content FTS5), `SessionHit`, `extract_snippet`, `query_tokens`, `SessionIndexError` (bilingual, fail-closed) |
| Tests | `tests/test_session_search.py` (35), `..._threads.py` (4), `..._processes.py` (1), `..._perf.py` (2) | 42 new tests; zero edits to existing tests |

API surface (kernel; CLI/bridge wiring is Stage F): `index_session(session_id, title, messages, source)`, `append_message(session_id, message, title?, source)` (the incremental append-event primitive), `remove_session`, `search(query, limit, offset)`, `rebuild()`, `doc_count()`, `close()`.

## B-1 design decisions

### 1. Tokenizer strategy — pre-normalized content through the single normalizer

SQLite's `unicode61` tokenizer folds case and strips diacritics, but it does
**not** fold Arabic yeh/kaf (U+064A/U+0643) onto Farsi yeh/keheh
(U+06CC/U+06A9), nor Persian/Arabic-Indic digits onto ASCII — those are
distinct code points, and no tokenizer option maps them. The only place
Dream's folding rules live is `dream.memory.normalize_fa`, so:

- **Index time:** `session_docs` stores `title_norm`/`body_norm` (normalized)
  as the FTS5-indexed columns, next to `title_orig`/`body_orig` (verbatim,
  for display and snippets). `unicode61 remove_diacritics 2` runs on already-
  normalized text — it contributes case-folding for Latin tokens and is
  harmless on the folded Persian.
- **Query time:** `query_tokens()` normalizes + tokenizes through the same
  import (`dream.memory._tokenize` + `normalize_fa`; identity re-pinned by
  test, same as Gate A).

**Trade-off, stated plainly:** text is stored ≈2× (original + normalized
shadow). Measured on the 10k-session corpus: **20.6 MB** for 10,000 sessions
including the inverted index — a few MB of shadow text on a personal corpus,
bought for the property the product is named after. A second trade-off:
normalized shadows are not user-facing, so snippets must map back to the
original (below).

Scope note (documented, not hidden): the guarantee is *spelling-variant*
retrieval at token level. ZWNJ and space are interchangeable in both
directions (`می‌خواهم` ⇄ `می خواهم`, pinned); the *merged* spelling
(`میخواهم`) is a different token under the shared normalizer — a morphology
matter, out of scope here exactly as it is on the memory-recall path.

### 2. Index schema — external-content FTS5, bm25 with deterministic tie-break

- **External content** (`content='session_docs', content_rowid='id'`): the
  content table is the single source of truth; the FTS table holds only the
  inverted index. *Rejected:* contentless (cannot serve content-derived
  results and cannot run the `'rebuild'` recovery command); self-contained
  FTS (would store the full text a second time inside the index structure).
- **Ranking:** `bm25(session_fts, 3.0, 1.0)` — a title hit is worth three
  body hits (pinned by `test_title_hits_outrank_body_hits`). Deterministic
  tie-break `ORDER BY rank ASC, d.id DESC`: equal scores resolve newest-
  first, stably, across repeated queries (pinned).
- **Prefix indexing: measured, not used.** The corpus benchmark runs at p95
  ≈ 27 ms without any `prefix=` option; adding prefix indexes would grow the
  index to accelerate a query class (left-anchored `tok*`) that session
  search does not issue. Numbers in MEM-GATES.md §B.2.

### 3. Lifecycle — incremental upserts, full rebuild, fail-closed version check

- Append events call `append_message` / `index_session`; each is one
  `BEGIN IMMEDIATE` transaction that deletes the old FTS entries (external
  content requires manual deletes with the *old* values), rewrites the
  content row, and inserts the new index entries. A searcher therefore sees
  only complete documents — old or new, never a blend (pinned under thread
  contention).
- `rebuild()` issues FTS5's `'rebuild'` command: re-derives the entire index
  from `session_docs`. **This is the documented recovery path** (kernel
  function; CLI/bridge exposure lands at Stage F with `search.*`).
- **Fail-closed open** (ledger's missing-vs-corrupt discipline): a missing
  file is a fresh index; a garbage/unreadable file, a `PRAGMA user_version`
  mismatch, or an unstamped/incomplete table set raises `SessionIndexError`
  with a bilingual message that names `rebuild()` — and the file is left
  **byte-identical** (pinned). Never silent reindex-and-continue.
- **Concurrent fresh-file open** (found by the process test, fixed): two
  processes opening the same *fresh* file race between "tables created" and
  "version stamped". The loser now recognizes the mid-init shape (exactly
  our tables, stamp 0), waits ≤ 5 s for the stamp, and proceeds; foreign
  unstamped shapes still fail closed. Verified over 5 consecutive runs.

### 4. Multi-writer safety

Same discipline as the Stage A bounded stores: one `threading.RLock` per
index (threads), `BEGIN IMMEDIATE` per upsert, `busy_timeout=5000` for other
processes. Pinned: writer-while-searcher (150 docs indexed under 3 spinning
searchers — no anomaly, no partial doc), concurrent appends to one session
(60 appends from 3 threads — every message kept, in order), concurrent
same-session upserts (last write wins, internally consistent), rebuild under
search (result count never dips), and two real OS processes writing the same
file at a `Barrier` (95 unique docs from 100 overlapping writes, zero
errors, zero duplicates).

### 5. Storage

Default `data/dream-session-index.db` (`DEFAULT_SESSION_INDEX_PATH`), under
Dream's data directory beside `dream.db` and `dream-bounded.db`. Environment
override hook: the constant mirrors `DREAM_BOUNDED_DB`'s pattern; the env
name `DREAM_SESSION_INDEX_DB` is consumed by callers at construction (Stage F
owner docs wiring). Tests pin that the default lives under `data/` and that
explicit paths are honored.

## Snippets — original text, word-aligned, bidi-safe

FTS5's SQL `snippet()` highlights where the *normalized* tokens matched — in
the normalized column; it cannot highlight the user's original spelling.
`extract_snippet()` therefore walks the original's whitespace words,
normalizes each word through the shared normalizer (reuse, not duplication),
marks words carrying a query token, and cuts a ~110-char window at word
boundaries around the first match, wrapping matched words in `[...]`.
Markers-and-ellipsis aside, the result is a verbatim contiguous slice of the
original — nothing is reordered, so RTL/mixed text cannot be mangled (pinned:
substring property + the Arabic-spelled word survives inside the brackets
when queried with Farsi spelling).

## RF-4 and machine gates

No existing test was edited. The module passes the M16 escaping gate (all
Persian literals are `\u06xx` escapes with glosses) and the conditional-
assertion gate (branching proofs live in non-test helpers). Ruff clean.

## Deliberately not in Stage B

- Bridge `search.*` RPC family + desktop ⌘P/palette surfaces — Stage F
  (protocol append-only + echo transport per guardrails).
- Optional LLM summarization of top-K — Stage F, and only when a model
  backend is available (keyword search is fully functional offline on echo).
