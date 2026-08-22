# MEM-A — Stage A: dual bounded memory stores with snapshot injection

**Date:** 2026-08-22
**Branch:** `arena/01a029da-dream` (base `29caacc`, the MP-01 merge plus owner CI updates)
**Scope:** PR-1 (kernel memory), first half. Gate evidence: [`MEM-GATES.md`](./MEM-GATES.md) §Gate A.
**Owner architect:** MNEMOSYNE · **Implementation:** SA-1 IRINI (stores/snapshot) with SA-5 VERITAS (tests, race audit, isolation audit)

## What was built

| Piece | File | Notes |
| --- | --- | --- |
| Bounded store kernel | `dream/memory_stores.py` | `BoundedStore` (SQLite, stdlib only), `BoundedSnapshot` (frozen dataclass), `BoundedMemory` (dual-store container), errors with bilingual, actionable messages |
| Agent integration | `dream/agent.py` | `Dream(..., bounded=...)` opt-in param; frozen per-session snapshot block in the system prompt; `agent_notes` / `user_profile` guarded tools (add/replace/remove, enum'd action) |
| Subagent isolation | `dream/subagents.py` + `dream/agent.py` | `INSTANCE_BOUND_TOOL_NAMES`; child grants of parent-bound closures are dropped |
| Tests | `tests/test_memory_stores.py` (38), `tests/test_memory_stores_threads.py` (5), `tests/test_memory_stores_processes.py` (2), `tests/test_memory_stores_agent.py` (17) | 62 new tests; zero edits to existing tests |

## Design decisions and why

### 1. Two stores, one module, one file per process

`BoundedMemory` opens two independent `BoundedStore`s (targets `memory` = agent
notes, `user` = user profile) on one SQLite file, default `data/dream-bounded.db`
(`DREAM_BOUNDED_DB` override; `:memory:` for ephemeral use). Each store owns its
connection, its `threading.RLock`, and its write transactions, so one writer per
store serializes in-process through the lock and cross-process through SQLite's
file lock (`BEGIN IMMEDIATE` + `busy_timeout=5000`), the same pairing
`MemoryStore` established for this repo.

### 2. Exact budgets, configurable in code

`NOTES_CAPACITY_CHARS = 2_200`, `PROFILE_CAPACITY_CHARS = 1_375` — the specified
budgets — plus `MIN_CAPACITY_CHARS = 64` validation. Both are constructor
arguments (`BoundedStore(target, capacity, ...)`, `BoundedMemory(notes_capacity=…,
profile_capacity=…)`); no magic numbers appear at call sites.

### 3. Capacity accounting and the header contract

`used = Σ len(entry) + (n−1) × len("§")` — the separator is part of the budget
because it is part of what the model reads. The snapshot renders
`[{percent}% — {used:,}/{capacity:,} chars]`, percent = `round(100·used/capacity)`.
The spec's example is pinned byte-for-byte: two entries totalling 1,474 chars on
a 2,200-char store render exactly `[67% — 1,474/2,200 chars]`
(`test_used_chars_counts_entries_and_separators`).

### 4. Overflow is an error, never a truncation

`add`/`replace` compute the post-write size inside the write transaction and
raise `StoreCapacityError` (bilingual: Persian guidance sentence first, English
sentence for logs) naming the header, the over-by amount, and the required
action — consolidate with `replace`/`remove` and retry in the same turn. Every
failure path rolls back: a rejected write leaves the store byte-identical
(pinned in three property tests plus the process-race tests).

### 5. Unique-substring matching through the single normalizer

`replace(old, new)` / `remove(old)` normalize both the fragment and every entry
through `dream.memory.normalize_fa` — the one Persian normalizer; the module
re-exports it and a test pins `dream.memory_stores.normalize_fa is
dream.memory.normalize_fa`. Zero matches → `EntryNotFoundError`; more than one →
`AmbiguousEntryError` listing bounded excerpts of every match so the agent can
pick a longer fragment. Arabic-spelled `كتاب` matches Farsi-spelled `کتاب` and
vice versa at the tool surface (pinned both directions, plus digit folding).

### 6. Frozen snapshot at session start; no read action

`Dream(bounded=…)` builds both snapshots at construction and renders one
constant prompt block (usage text + labelled sections + capacity headers +
`§`-joined entries). The block is a **constant string for the session**: mid-
session tool writes land in the stores and in the tools' own result payloads
(which return the fresh header and content), never retroactively in the running
session's prompt. `reset_session()` — the new-session boundary — re-freezes.
There is no read tool: the snapshot is already in the prompt and every mutation
returns the full fresh state, which keeps the surface at three actions without
hiding anything from the agent.

### 7. Tools

`agent_notes(action, text, old, new)` and `user_profile(...)` — `guarded` risk
(local, reversible, logged), same tier as `remember_fact`. `action` is a
`Literal` so the generated schema carries the `["add","replace","remove"]` enum.
An unknown action string is a clean `ValueError` through the tool boundary.

### 8. Subagent isolation (fail-closed audit finding, fixed)

`build_child_tools` previously granted any name found in the post-child-init
registry snapshot. A spec granting `agent_notes` would have received the
**parent's** closure (a child `Dream` never registers bounded tools) — a hole in
the "children never reach parent memory" invariant. `INSTANCE_BOUND_TOOL_NAMES`
now lists every store-bound closure name; a granted instance-bound name is
dropped when the child did not rebind it (identity check against the parent
snapshot). Memory/reminder names still pass because the child rebinds them to
its ephemeral store; stateless module-level tools (`calculate`, …) are
untouched. Pinned by `test_subagents_never_receive_the_parents_bounded_tools`,
which also re-pins byte-identical parent-registry restoration.

## RF-4 discipline (existing tests)

No existing test was edited or deleted. The full pre-existing suite (1748
passed / 11 skipped) passes unmodified alongside 62 new tests → 1810 / 11.
`tests/test_m16_escaping.py` initially flagged the new module docstring (raw
Persian glyphs); fixed in the module (escapes), not by touching the gate.

## Guardrail compliance

- **Zero new runtime dependencies** — `sqlite3`, `threading`, `dataclasses`, all stdlib.
- **Single normalizer** — imported, never duplicated; identity-pinned by test.
- **Privacy** — stores live under Dream's data directory; nothing leaves the machine; no telemetry.
- **Config strictness** — no tsconfig/eslint changes (desktop untouched); ruff clean; no suppressions.
- **Bridge protocol** — untouched in Stage A (append-only `memory2.*` lands with the UI stage per plan).

## Not in Stage A (tracked for later stages)

- Consolidation/dedupe pass with reviewable diff — Stage E (CHRONOS/IRINI).
- Bridge RPC family (`memory2.*`) + desktop dual-store UI — Stage F (LUMEN-UI), protocol append-only with echo transport.
- Memory nudges — Stage E.
