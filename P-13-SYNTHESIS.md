# P-13 Synthesis Report — Memory Explorer & Reminder Authoring

> Status: **awaiting PM approval**. No production file has been edited. This
> report is the synthesis gate artifact required before implementation.

- Base main SHA: `0b5617c0d444501644559c35f11030c9526760f4`
  (`feat(scheduler): deliver scheduler UI and execution safety hardening (#126)`)
- Local branch `arena/01a0734c-dream` is clean and identical to `origin/main`
  at that SHA (verified via `git fetch` + `rev-parse`).
- Roadmap target: `MASTER_CHECKLIST.md` §2.3 — "Memory explorer + timeline;
  reminders — explorer/timeline complete; **reminder authoring remains**."

---

## 1. Current memory architecture (Agents A, E)

### 1.1 Data flow map

```
React (apps/desktop/src/routes/memory.tsx)
  └─ lib/bridge/memory.ts  (memory.list/search/get/update/delete/count/create)
       └─ JSON-RPC → dream/bridge/methods.py  (DreamMethods.memory_*)
            └─ dream/memory.py MemoryStore (SQLite + FTS5, per-user rows,
               RLock-guarded writes, soft-archive `forget(hard=False)` default)
```

- `Memory` model: `id, kind(semantic|episodic|procedural), content, tags,
  importance(0–1), created_at, last_used_at, use_count, source, archived,
  pinned, score`. Provenance = `source` + timestamps + use counts.
- `normalize_fa` (single source of truth): NFKC → Persian/Arabic-Indic digit
  folding → Arabic→Persian char unification → diacritics strip → ZWNJ→space →
  whitespace collapse. Applied on write **and** read; `_stem_fa` suffix stemmer
  for retrieval.
- `memory.list` (bridge): kind/date/importance/search filters, 4 sort modes,
  cursor pagination hard-capped at `limit ≤ 500`; normalised substring match.
- `memory.search` → `MemoryStore.recall` (FTS5 + synonym expansion, LIKE
  fallback). `memory.count` → per-kind counts for filter tabs.
- Updates: `memory.update` → `MemoryStore.update_memory` (validates kind,
  re-normalises, preserves id/created_at/source). Deletes: soft archive by
  default, `hard=true` erases the row — the UI describes this truthfully.
- A second, separate system `dream/memory_stores.py` (BoundedStore,
  `memory2.*` RPC family) is the frozen bounded-prompt store; exposed on its
  own "Bounded" tab. Out of scope for P-13 beyond not breaking it.

### 1.2 State & mutation invariants (verified)

- All writes under `store._lock`; per-`user_id` row scoping on every query
  (`test_memory_tenant.py`).
- Duplicate detection (Jaccard ≥ 0.80 on stemmed tokens) and contradiction
  detection (0.80 shared-prefix threshold) run on `remember` only.
- Atomicity: single-statement INSERT/UPDATE + commit inside the lock; no
  cross-store transactions needed by the explorer.
- Corruption recovery: SQLite WAL journal; no repair path — corruption fails
  closed at open. No defect found requiring core memory changes.

## 2. Current reminder / scheduler architecture (Agents C, E)

Two **pre-existing, independent** systems:

### 2.1 Legacy reminders (`dream/reminders.py`, `MemoryStore` methods)

- `Reminder(id, user_id, text, due_at, next_due, repeat_days|repeat_months,
  last_fired_at, created_at, active, anchor_day)` in the `reminders` table +
  `reminder_deliveries` history (one row per destination; M21 FK cascade).
- Jalali-aware repeats (`advance_due_date`, Esfand clamping, 31st anchor);
  `parse_persian_date` resolves Persian phrases («فردا», «پانزدهم مهر», …).
- Delivery: **no daemon**. Surfaced via prompt injection
  (`agent.py: prompt_reminders`), `check_due_reminders` (terminal/telegram),
  CLI, and the Tkinter `desktop.py` panel UI.
- **No bridge RPC family exists.** `reminder_to_dict` in
  `dream/bridge/methods.py:324` is dead code (registered nowhere) — evidence
  the desktop surface was planned but never wired.

### 2.2 P-12 scheduler (`dream/scheduler.py`, `dream/cron.py`, `dream/nl_schedule.py`)

- `Schedule(id, name, description, cron_expression, natural_language, prompt,
  session_id, enabled, last_run, next_run, created_at, max_runs, run_count,
  require_approval)` + `ScheduleRun` history rows (running → success | error |
  approval_denied), written **before** execution (crash-visible).
- RPC family: `schedule.create|list|get|update|delete|toggle|history|preview|
  run_now|approve` — full CRUD already in `dream/bridge/methods.py`.
- Daemon: exactly one lazily-built `SchedulerDaemon` per bridge
  (`_scheduler_daemon()`, started once by `server.py:575`); 30 s poll;
  injectable clock; atomic `claim_due_schedule` (no double-run);
  `recover_interrupted_runs` on start; drain-then-cancel stop; **fail-closed
  approval gate** (timeout 300 s → denied; missing gate → denied).
- `schedule.preview` = `nl_to_cron` (20+ EN/FA phrasings, no model call) +
  `describe_cron` + upcoming runs; never raises on partial input.
- Cron times are machine-local naive datetimes; UI shows dual
  Gregorian + Jalali (`utils/time.ts jalaliDateTime`).

### 2.3 Reminder lifecycle state machine (as it will ride the scheduler)

```
            create (enabled)
                 │
   ┌─────────────▼──────────────┐
   │ active(enabled) ◄───────── toggle ───────┐
   │  next_run = cron.after(now)              │
   └───────┬──────────────────────────────────┘
      due & claimed atomically (single worker)
           │
   require_approval? ── yes → approval gate ── deny/timeout → run row
           │ no                                  "approval_denied" (fail-closed)
           ▼
   run row "running" → runner(prompt) → "success" | "error"
           │
   run_count++; next_run advanced; exhausted when run_count ≥ max_runs
   delete → row + history removed (existing cascade)
```

## 3. API / bridge contract table (Agent E)

| Method | Python | TS wrapper | Echo runtime | Rust |
|---|---|---|---|---|
| `memory.list` | ✅ | ✅ | ✅ | passthrough |
| `memory.search` | ✅ | ✅ | ✅ | passthrough |
| `memory.get/update/delete/count/create` | ✅ | ✅ | ✅ | passthrough |
| `memory2.snapshot/add/replace/remove` | ✅ | ✅ | ✅ (echo-memory2) | passthrough |
| `schedule.create/list/get/update/delete/toggle/history/preview/run_now/approve` | ✅ | ✅ | ✅ (EchoScheduleRuntime) | passthrough |
| `reminder.*` | ❌ **none registered** | ❌ | ❌ | — |

Rust bridge (`src-tauri/src/bridge/`) is method-agnostic framing/dispatch —
**no Rust changes required** for any planned scope. No mismatches found
between Python and TS for existing memory/schedule methods.

## 4. Privacy & security threat model (Agent D)

| Threat | Current state | Finding |
|---|---|---|
| Memory/reminder content in logs | Bridge log filter value-scans every line (SEC Stage C G-17); scheduler failures log schedule **id** only (`logger.debug`), though `exc_info` tracebacks could embed prompt text at debug level | Pre-existing P-12 behavior; leave untouched; residual risk noted |
| Search terms in URL state | Memory/scheduler routes keep filters in component state only; no query params | ✅ no leak — must be preserved in new UI |
| Delete confirmation | MemoryDrawer + ConfirmDialog (focus-restoring, accessible) | ✅ pattern to reuse |
| Access scope | Every store query user-scoped; gateway scope boundaries untouched | ✅ |
| Secrets | Keychain injection at backend build; never persisted | ✅ unchanged |
| Dangerous scheduled work | `require_approval` + L3 floor + cron context denies dangerous tools | ✅ unchanged; reminders must not bypass |
| Telemetry/analytics | None exists | ✅ none added |
| Export/share | None exists in memory UI | None added (non-goal) |

**Authorization matrix:** all P-13 surfaces are local-user scope via the
authenticated sidecar IPC; no new remote surface; Web Gateway untouched.

## 5. UI state inventory & a11y/RTL findings (Agents B, G)

Memory explorer (complete): filters/list/timeline/drawer/bounded tabs;
loading skeletons, empty states, error+retry, offline banner, aria-live
counts, VirtualList bounded rendering, `dir="auto"` rows, `ltr-island` for
cron, debounced inputs, aborted stale requests. Scheduler route (complete):
same state discipline + approval queue poll (4 s) + Jalali dual display.
**Gaps:** none requiring changes to existing memory UI; the only missing
Phase-2 surface is **reminder authoring** (no reminder concept anywhere in
the React app — verified by grep).

Locales: 8 files (en, fa, zh-CN, ja, es, de, fr, ko) enforced by
`tools/check_locales.py` + `npm run locales:check` (structure + placeholder
parity; missing keys fail CI). New strings must land in all 8.

## 6. Exact findings & severity

| # | Severity | Finding |
|---|---|---|
| F-1 | High (feature gap) | No reminder authoring surface for the desktop app; `reminder_to_dict` bridge helper is dead code |
| F-2 | Medium (design) | Legacy reminders have no RPC and no desktop delivery path; wiring them into the desktop would require a second engine — forbidden |
| F-3 | Low | `schedule.list` cannot filter by schedule class; a reminders tab would otherwise have to filter by naming convention (fragile, untruthful) |
| F-4 | Low | `nl_to_cron` has no one-off date phrasing («فردا ساعت ۹») — one-off reminders need a date/time input compiled to `m h dom mon *` cron + `max_runs=1` |
| F-5 | Info | Cron is machine-local time; UI must keep dual Gregorian+Jalali display (existing convention) |
| F-6 | Info | Duplicate-submit protection in dialogs is disable-on-busy (no idempotency key) — acceptable, keep pattern for reminders |
| F-7 | Info | Memory core, explorer, timeline, bounded stores: **no defects found** — no core memory changes proposed |
| F-8 | Info | No bulk memory operations exist in the contract — none will be added |

## 7. Proposed scope (for approval)

**Architecture — reminders are schedules.** A reminder is authored *through
the existing scheduler contract* (`schedule.*`), tagged by a new additive,
default-null-safe `kind` column (`'task'` | `'reminder'`, default `'task'`).
The P-12 daemon, claim path, approval gate, and history are **untouched**;
reminders ride them. No second engine, no second worker, no legacy-table
bridging. Legacy `dream/reminders.py` (CLI/Tkinter/telegram/prompt paths)
is left byte-for-byte unchanged.

### Files in scope (planned)

| File | Change |
|---|---|
| `dream/scheduler.py` | Additive: `kind` field on `Schedule`, idempotent column migration in `ensure_schedule_tables`, `kind` in `create_schedule`/`update_schedule`/`schedule_to_dict`, optional `kind` filter in `list_schedules`. Daemon/claim/approval/history code paths unchanged |
| `dream/bridge/methods.py` | `schedule_create`/`schedule_update`/`schedule_list` accept optional validated `kind` (backward compatible; absent → `'task'`) |
| `apps/desktop/src/lib/bridge/types.ts` | `BridgeSchedule.kind`, list params |
| `apps/desktop/src/lib/bridge/schedule.ts` | `kind` in draft/patch/list |
| `apps/desktop/src/lib/bridge/echo-subagents.ts` | `EchoScheduleRuntime` honors `kind` |
| `apps/desktop/src/routes/memory.tsx` | Third tab "Reminders" (lazy or inline) |
| `apps/desktop/src/components/memory/reminder-*.tsx` (new) | Reminder list card + authoring/edit dialog (text, rhythm NL/cron preview, optional one-off date+time → cron + max_runs=1), enable/disable, run-now, history, delete confirmation |
| `apps/desktop/src/components/memory/reminder-model.ts` (new) | One-off date+time → cron compile (deterministic, unit-tested) |
| `apps/desktop/src/locales/*/memory.json` ×8 | Reminder strings incl. Persian |
| `apps/desktop/src/routes/memory.test.tsx` (+ new component tests) | Frontend tests |
| `tests/test_scheduler.py` or new `tests/test_p13_reminder_authoring.py` | Backend tests |
| `P-13-AUDIT.md` (new, post-implementation) | Audit report |
| `MASTER_CHECKLIST.md` | Tick 2.3 when done |

### Files explicitly out of scope

`dream/reminders.py`, `dream/memory.py`, `dream/memory_stores.py`,
`dream/cron.py`, `dream/nl_schedule.py`, `dream/agent.py`, `desktop.py`,
`cli.py`, `dream/bridge/server.py`, all `gateway.*`/`remotegw`/Web-Gateway
code, workflows (`.github/`), release tooling, Rust files, provider routing,
billing/quota, `SEC-*` phase implementations, bounded stores, CHANGELOG
(no v0.4.7), every other route/component.

### Migration & compatibility risks

- `kind` column addition is idempotent `ALTER TABLE` inside
  `ensure_schedule_tables` (same pattern as `_ensure_user_column`); existing
  rows default `'task'`; old clients omitting `kind` behave identically.
- Risk: scheduler page shows reminders mixed with tasks → mitigated by
  `kind` filter on its list call (default task view) — PM decision below.
- No data migration needed; rollback = revert commit (column is ignored by
  old code once present — SQLite tolerates the extra column).

## 8. Deterministic test plan

Backend (fake clocks, tmp dirs, no network, no sleeps):
- `kind` round-trip (create/update/serialise/filter); default `'task'` for
  legacy callers and pre-existing rows; invalid `kind` rejected **before**
  persistence; migration idempotence (open store twice).
- Bridge: `schedule.create kind='reminder'`; `schedule.list kind` filter;
  absent kind → `'task'` (backward compat); invalid → `-32602`.
- P-12 invariants intact: daemon tick with injected clock ignores `kind`;
  claim/execute/approval-timeout fail-closed re-verified via existing suite
  (`tests/test_scheduler.py`, 75 tests, must stay green).
- One-off compile: date+time → `m h dom mon *` fires exactly once;
  `next_run_after` truthfulness with fixed `now`.

Frontend (vitest + testing-library, echo/state transports, fake timers):
- Reminders tab: empty/loading/error+retry/offline states.
- Create: text+rhythm live preview via `schedule.preview` echo; invalid
  rhythm blocks submit; one-off date+time compiles cron and sets
  `max_runs=1`; duplicate submit prevented (busy disable); confirmation
  wording truthful (no recovery claim).
- Edit/enable/disable/run-now/delete/history via existing `schedule.*`.
- Privacy: no route/URL ever receives reminder text; error surfaces show
  RPC errors only.
- A11y/RTL: dialog names + labels, focus restore, aria-live status,
  `dir="auto"`/mirroring checks per existing stage-D patterns.
- Locale completeness: `npm run locales:check` fails on missing keys.

Verification commands (all will be executed and recorded):
`python -m pytest -q` · `python -m ruff check .` · `python -m mypy .` ·
targeted `pytest tests/test_scheduler.py tests/test_bridge_memory_skills.py
tests/test_bridge_subagent_schedule.py` · `npm run typecheck lint
format:check test build` · `npm run locales:check`. Rust untouched → cargo
jobs run unchanged in CI.

## 9. Unresolved PM decisions

1. **Reminder model** — additive `kind` column on schedules (recommended)
   vs. zero-backend convention (name-prefix filter).
2. **Placement** — Reminders tab inside Memory page (recommended, matches
   checklist §2.3) vs. a section in the Scheduler page.
3. **Scheduler page behavior** — default to task-only list (recommended,
   with reminders visible on the Memory page) vs. show all with a badge.
4. **One-off reminders** — explicit date+time input compiled to cron +
   `max_runs=1` (recommended) vs. NL-rhythm-only authoring.
