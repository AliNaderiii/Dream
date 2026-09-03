# SEC-08 — BoundedStore Concurrency Hardening Audit (STAB-03)

- **Repository:** Dream v0.4.6 (target release v0.4.7)
- **Base commit:** `1e451cddd79825aeed0ae006cbcdc6122b62f2c3` (`fix(agent): harden user-agent validation and versioning (SEC-07)` — the tip of `main`, i.e. Dream v0.4.6 + merged SEC-01 … SEC-07)
- **Working branch:** `arena/01a0670c-dream` (this session is fixed to this branch by the Arena environment; the brief's `fix/p0-security-stability` name could not be used — see Coordination Needed)
- **Scope actually touched:** `dream/memory_stores.py` (BoundedStore / BoundedSnapshot / BoundedMemory docstrings + the write path only), `tests/test_bounded_store_concurrency.py` (new), `SEC-08-AUDIT.md` (this file). Nothing else.

## 1. BoundedStore state inventory (audited before editing)

`rg -n "class BoundedStore|BoundedSnapshot|snapshot\(|replace\(|\.add\(" dream tests` at the base commit.

| State | Kind | Where read/written |
|---|---|---|
| `target`, `capacity`, `separator`, `path`, `user_id` | immutable scalars (str/int), assigned once in `__init__` | read by every method; never reassigned after construction |
| `self._lock` (was public surface `RLock`) | `threading.RLock`, one per store | every public method |
| `self.conn` (now **`self._conn`**) | `sqlite3.Connection`, `check_same_thread=False`, autocommit (`isolation_level=None`), WAL, `busy_timeout=5000` | **the only mutable state**: all rows of `bounded_entries` live in SQLite, not in an in-memory collection |
| `BoundedSnapshot` fields | `target`, `capacity`, `entries: tuple[str, ...]`, `separator` — frozen `slots` dataclass | built fresh on every `snapshot()` call |
| `BoundedMemory.notes` / `.profile` / `.path` | public references to two independent `BoundedStore` objects | constructed once in `__init__`; never reassigned |

Key structural facts:

* **No in-memory entry collection exists** — the store's mutable content is entirely in SQLite. So "synchronize every access to mutable state" reduces to: *every access to the connection runs under the store lock*, and *every check-plus-mutate cycle is one transaction*.
* **No callbacks, no user-supplied equality hooks.** The only callable that runs "while a result is being computed" is `BoundedSnapshot`'s pure properties (`header`, `text`, `used_chars`, `percent`) and the pure `normalize_fa` string mapper; both are side-effect-free and cannot re-enter the store. There is nothing to defer outside the lock.
* **`BoundedSnapshot` is fully detached:** frozen + slotted dataclass holding a *fresh* `tuple` of immutable `str`s (built from `fetchall` inside `snapshot()`). Mutating snapshot elements is impossible (strings), reassigning fields is refused (frozen), and adding attributes is refused (slots). **Decision on element copying:** no defensive copy of elements is needed because the elements are immutable `str`s; only the container needs to be a fresh copy, which it is.

## 2. Lock coverage table (after hardening)

Every mutable-state access in `BoundedStore` / `BoundedMemory`:

| Method / access | Takes lock? | Defensive copy under lock? | Transaction? | Callbacks under lock? | Returns |
|---|---|---|---|---|---|
| `__init__` | n/a (single-threaded construction; object not yet shared) | n/a | `executescript` (autocommit DDL) | none | — |
| `close()` | yes (`_lock`) | n/a | closes `_conn` (idempotent) | none | `None` |
| `__enter__` / `__exit__` | via `close()` | — | — | none | `self` / `None` |
| `snapshot()` | yes | yes — fresh `tuple[str, ...]` of immutable strings, immutable scalars copied by value | read (no write tx) | none | detached `BoundedSnapshot` |
| `_entries_locked()` (private) | must be held by caller (documented) | fresh tuple | inside caller's unit | none | `tuple[str, ...]` |
| `add(text)` | yes — whole unit via `_locked_write` | reads inside tx | **one** `BEGIN IMMEDIATE` … `COMMIT`: pos check + capacity check + `INSERT` + commit | none | fresh `BoundedSnapshot` built under the lock **after** commit |
| `replace(old, new)` | yes — whole unit via `_locked_write` | reads inside tx | **one** `BEGIN IMMEDIATE` … `COMMIT`: unique-substring match + capacity check + `UPDATE` + commit | none | fresh `BoundedSnapshot` after commit |
| `remove(old)` | yes — whole unit via `_locked_write` | reads inside tx | **one** `BEGIN IMMEDIATE` … `COMMIT`: match + `DELETE` + commit | none | fresh `BoundedSnapshot` after commit |
| `_match_locked()` (private) | must be held by caller (documented) | — | inside caller's write tx (so match and mutation are atomic) | none | `(pos, entry)` |
| `_capacity_error(over_by)` (private) | re-enters `RLock` (same thread — safe) and may run inside the open write tx before any write | fresh snapshot tuple | read-only SELECT (identical to committed state: no write has happened yet) | none | `StoreCapacityError` |
| `BoundedMemory.snapshots()` | per store: yes, **in sequence** (notes then profile) | per store, as above | per store | none | dict of two *individually* consistent snapshots (not one global instant — see §6) |
| `BoundedMemory.store(target)` | no (resolves a reference; stores are shared objects by design) | — | — | none | `BoundedStore` |

* Lock type unchanged: the existing `threading.RLock`, the same type `dream.memory.MemoryStore` uses. RLock (not `Lock`) is required because `_capacity_error → snapshot()` re-enters the same thread's lock, and `add`/`replace`/`remove` build their return snapshot after the unit (the existing `test_nested_lock_use_does_not_deadlock` pins this).
* **The connection handle is now private (`_conn`).** It was a public attribute at base: any caller could run `store.conn.execute(...)` outside the lock and break the capacity invariant. No code in the repository reads it on a bounded store (verified: the only `.conn` consumers are `dream/reminders.py` and `dream/scheduler.py`, both on the *different* `MemoryStore` class, which is out of scope). Renaming an undocumented internal attribute is not a contract change for the module's documented API (`__all__`, docstrings, `add/replace/remove/snapshot/close`, `BoundedMemory` methods).
* **No lock is ever held across a callback, blocking I/O beyond SQLite's own lock wait, or unknown code.** The only blocking operation under the lock is the SQLite call itself; `BEGIN IMMEDIATE` can wait up to `busy_timeout` (5 s) for a *cross-process* writer — that wait is intrinsic (the transaction is on this connection, so releasing the in-process lock would not help), and it cannot deadlock: the only cross-process resource is the SQLite file lock, and no thread holds the file lock while waiting on another thread's in-process lock in a cycle (same-process waiters block on the RLock, not the file lock).

## 3. The concrete baseline defect found and fixed

**A keyboard interrupt inside a write bricked the store forever.** The base code wrapped each write in `except Exception:` and rolled back there — but `KeyboardInterrupt` is a `BaseException`, so a Ctrl-C landing on any bytecode between `BEGIN IMMEDIATE` and `COMMIT` propagated without rollback, leaving the read-write transaction **open on the shared connection**. Every later write then failed with `OperationalError: cannot start a transaction within a transaction` until process restart.

Reproduced at the base commit with the base code's exact write structure (probe, verbatim):

```text
$ python -c '...old_style_write with KeyboardInterrupt raised at the INSERT line...'
in_transaction after interrupt: True
recover FAILED: OperationalError - cannot start a transaction within a transaction
```

(No `unittest.mock` patching of `sqlite3.Connection` is possible — it is an immutable type with read-only attributes — so the probe raised the interrupt from inside the write unit, which is exactly what a real SIGINT does at bytecode level.)

Fix: the new `_locked_write` contextmanager catches `BaseException`, rolls back (gated on `conn.in_transaction`), and re-raises. Pinned by `test_interrupt_inside_the_write_unit_leaves_no_open_transaction`, which fails against the base structure and passes now.

Secondary hardening in the same change:

* The three duplicated `except Exception: try: ROLLBACK except sqlite3.OperationalError: pass` blocks (a **silent exception swallow**) were replaced by the single disciplined unit: the no-op-rollback swallow is gone because rollback is now gated on `in_transaction`; a rollback that fails for a *real* reason now propagates instead of being hidden.
* `_capacity_error` no longer needs a manual `ROLLBACK` first; the unit rolls back after the error is constructed (the error's header snapshot is identical — taken before any write, so committed state either way).

## 4. Atomicity guarantees (per public method)

* **`add`:** row-position computation, capacity check, insert, and commit are one `BEGIN IMMEDIATE` transaction under the RLock. From a caller's perspective `add` is atomic: a concurrent add/replace/remove (same process: RLock; other process: SQLite write lock) is entirely before or after. Two concurrent adds can never produce a duplicate row of the *same logical write* (each accepted add appears exactly once — pinned by the 100-thread stress test), and a write can never land past capacity. On overflow the store is left untouched and a `StoreCapacityError` is returned with the *pre-write* header.
* **`replace`:** unique-substring match, capacity check, and update are one unit, so the fragment cannot match something else between check and update (no lost update, no torn replacement). Missing → `EntryNotFoundError`, multiple → `AmbiguousEntryError`, overflow → `StoreCapacityError`; in all three cases nothing is written. Ordering and `updated_at` semantics are unchanged: replacement keeps the entry's `pos` (order preserved) and stamps `time.time()`.
* **`remove`:** match + delete one unit.
* **Capacity enforcement:** the check and the mutation are in the same transaction *and* under the same lock, so the budget can never be exceeded by interleaving — in-process (RLock) or cross-process (`BEGIN IMMEDIATE` makes the check read the latest committed state under the write lock; `test_two_processes_racing_the_capacity_budget_serialize` and the new 100-racer thread test pin both).
* **Failed or interrupted writes are invisible:** any exception path rolls back before propagating (§3).

## 5. Snapshot-copying policy

* `snapshot()` runs under the lock and returns a **detached** `BoundedSnapshot`: a fresh `tuple` (never the store's live tuple — pinned by `first_a.entries is not first_b.entries` for non-empty content), of immutable `str` elements (no element copy needed — documented decision, §1), inside a frozen slotted dataclass.
* Consequences, all pinned: no partially-updated snapshot (a reader sees a state that was committed before its `SELECT` started — WAL + the lock); caller mutation cannot reach the store (frozen dataclass refuses it); snapshots survive later mutations (`frozen.entries` unchanged after `add`/`replace`/`remove`, including under 50-thread concurrent growth); the return annotation `-> BoundedSnapshot` describes the actual object exactly.
* Budget: unchanged (< 5 ms, existing test still passes).

## 6. Capacity / deduplication behavior (unchanged by design)

* **Capacity:** `used_chars` = Σ len(entry) + (n−1)·len(separator); an add/replace that would exceed `capacity` raises `StoreCapacityError` and writes nothing — overflow is an error, never a truncation, and **nothing is silently dropped** beyond that documented policy. Exact-fit is allowed (`used + needed == capacity` succeeds).
* **Deduplication:** the store has **no value-level deduplication** — `add("dup")` twice stores two entries, and 300 threads adding `"dup"` leave 300 entries (pinned by `test_duplicate_adds_from_hundred_threads_all_land`). What *is* guaranteed under concurrency is row integrity: no lost write, no duplicated row, unique `pos`, insertion order per writer. This matches the documented contract (the tool description tells the agent to consolidate near-duplicates with `replace`, i.e. duplicates are expected to exist).
* **`BoundedMemory.snapshots()`:** per-store snapshots are each atomic under their own lock; the pair is taken in sequence (notes then profile) and is *individually* consistent, not a single global instant. The session-start prompt contract only ever needs the per-store form, so no cross-store transaction was added (adding one would introduce a lock-ordering surface for no contract benefit).

## 7. Stress-test methodology and repetition

New file `tests/test_bounded_store_concurrency.py` — 8 test functions, each race repeated **`REPEATS = 10` times on fresh stores inside the test** (no external repeat plugin). Coordination is exclusively `threading.Barrier` + `ThreadPoolExecutor` + `concurrent.futures.wait` with one hard **120 s per-race deadline** (a deadlock fails the test in bounded time; no sleeps anywhere in the file).

| Test | Race | Invariants |
|---|---|---|
| `test_hundred_threads_add_unique_values_exactly_once` | 100 threads × 10 unique adds | all 1,000 present exactly once; per-writer order preserved; `used ≤ capacity` |
| `test_hundred_readers_see_only_consistent_snapshots_while_writers_add` | 100 readers × 150 snapshots ‖ 10 writers × 20 adds | every snapshot: `used ≤ capacity`, no duplicate/phantom entries; sampled (every 20th) full per-writer prefix law (torn-write detector) |
| `test_concurrent_add_and_replace_never_lose_or_duplicate` | 25 replacers ‖ 10 adders, barrier start | all 100 replacements landed exactly once, all 200 adds present, no duplicates, `used ≤ capacity` |
| `test_duplicate_adds_from_hundred_threads_all_land` | 100 threads × 3 identical adds | exactly 300 `"dup"` entries; no dedup, no loss |
| `test_hundred_racers_for_one_last_slot_fit_exactly_one` | 100 racers for exactly one fitting slot | exactly **one** winner; final `used == capacity` exactly |
| `test_snapshots_are_detached_copies_not_live_views` | snapshot, then 50-thread growth | frozen/`slots` refusal; `is not` fresh tuples; earlier snapshots unchanged after growth |
| `test_both_stores_hold_their_budgets_under_cross_store_traffic` | 25 notes writers + 25 profile writers + 50 readers on **one real file** (two connections) | both default budgets (2,200 / 1,375) hold at all times; every accepted add present exactly once — exercises SQLite's file lock, not just the in-process RLock |
| `test_interrupt_inside_the_write_unit_leaves_no_open_transaction` | KI raised inside the write unit | `in_transaction is False` afterwards; store still accepts writes (fails on base code, §3) |

Total per full file run on this 2-core sandbox: ~52–56 s for 80 race iterations.

## 8. Commands run and results

All commands from the repository root, `.venv` (Python 3.11.2, pytest 9.1.1, ruff 0.16.5), fresh `pip install -e ".[dev]"`.

```text
$ .venv/bin/python -m pytest -q tests/test_bounded_store*.py tests/test_memory_stores*.py
70 passed in 65.15s            # 62 pre-existing (unmodified) + 8 new

$ .venv/bin/python -m pytest -q tests/test_bounded_store_concurrency.py   # run #1 (post-restructure)
8 passed in 56.06s
$ .venv/bin/python -m pytest -q tests/test_bounded_store_concurrency.py   # run #2 (flake check)
8 passed in 53.28s             # earlier iterations: 1 failed (a test-side barrier bug, fixed)
                                                                       # and 8 passed (pre-restructure)

$ .venv/bin/ruff check dream/memory_stores.py tests/
All checks passed!
$ .venv/bin/ruff check .       # the CI lint step
All checks passed!

$ .venv/bin/python -m pytest -q
3375 passed, 14 skipped in 178.55s   # base was 3367 passed, 14 skipped: +8, all new

$ .venv/bin/python tools/check_suite_count.py
Suite count check passed: 3378 tests collected (minimum required: 652).   # base: 3370

$ .venv/bin/python tools/check_commit.py HEAD   # pre-commit, HEAD = base 1e451cd
Commit rule violations for HEAD:
  - Invalid commit author name: 'arena-ai-coding-agent[bot]'. Expected 'Ali Naderi'.
  - Invalid commit author email: '298482267+arena-ai-coding-agent[bot]@users.noreply.github.com'.
(pre-existing: the base commit's local author metadata. The SEC-08 commit is
authored with the project-required name/email, exactly as SEC-01..07 were, and
re-checked after committing — see the final report.)

$ git diff --check
(clean)
```

Mutation-style verification (performed manually at base, then reverted): the interrupt probe in §3 fails on the base write structure and passes with `_locked_write`; reverting `BaseException` → `Exception` in the unit makes `test_interrupt_inside_the_write_unit_leaves_no_open_transaction` fail. The rest of the suite passed **without modification** before and after (62/62), so single-threaded ordering, deduplication, capacity, matching, and snapshot semantics are provably unchanged.

Final scope audit: `git status` shows exactly `M dream/memory_stores.py`, `?? tests/test_bounded_store_concurrency.py`, `?? SEC-08-AUDIT.md`; `rg -n "class BoundedStore|snapshot\(|replace\(" dream/memory_stores.py tests` confirms the only BoundedStore changes are inside `dream/memory_stores.py`.

## 9. Remaining risks and coordination items

**Remaining risks (accepted, documented):**

1. **`busy_timeout` wait under the lock.** `BEGIN IMMEDIATE` can block up to 5 s under the RLock while a *cross-process* writer holds the SQLite file lock. Intrinsic to keeping check+write atomic on one connection; bounded; cannot deadlock (see §2). A pathological 5-s stall is a performance issue only — no correctness loss.
2. **Use-after-close is undefined** (as at base): an operation racing `close()` from another thread may raise `sqlite3.ProgrammingError` from the stdlib. `close()` itself is lock-protected and idempotent. No in-repo caller does this; a dedicated `StoreClosedError` would be a new public exception type and was deliberately not added.
3. **Cross-store pair is not a global instant** (documented in `BoundedMemory.snapshots()`; §6).
4. **Stress coverage is in-process + real-file multi-connection.** Cross-*process* races are still covered by the pre-existing `tests/test_memory_stores_processes.py` (2 and 4 real OS processes), unmodified and passing; the new file adds no process-level races beyond what exists.

**Coordination Needed:**

1. **Branch name.** This Arena session is fixed to `arena/01a0670c-dream`; the brief's `fix/p0-security-stability` could not be used (same situation as SEC-07 — that branch does not exist in this checkout either). The PR targets `main` as required.
2. **`conn` → `_conn` rename.** No in-repo consumer of a bounded store's connection exists, but any *external* embedder reading `store.conn` would need `store._conn`. Flag for the v0.4.7 release notes.
3. **CI runtime.** The stress file adds ~1–2 min per CI job (4 Python versions) on GitHub runners; expected, no action requested.
4. Nothing else requires changes in agent logic, browser/security code, Rust, frontend, workflows, or other sub-agents' files.
