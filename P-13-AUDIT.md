# P-13 Audit — Memory Explorer & Reminder Authoring

## Base and scope

- **Base main SHA:** `0b5617c0d444501644559c35f11030c9526760f4`
  (`feat(scheduler): deliver scheduler UI and execution safety hardening (#126)`)
- **Roadmap item:** `MASTER_CHECKLIST.md` §2.3 — memory explorer + timeline
  were already complete; reminder authoring was the remaining work. §2.3 is
  now checked.
- **PM decisions (approved before implementation):** additive `kind` column;
  Reminders tab on the Memory page; Scheduler page filters to `kind=task`;
  one-off reminders compiled from date+time to cron with `max_runs=1`;
  three-way `max_runs` update contract (omitted → keep, explicit `null` →
  clear, integer → set).

### Changed files (complete list)

| File | Change |
|---|---|
| `dream/scheduler.py` | `SCHEDULE_KINDS`/`DEFAULT_SCHEDULE_KIND`; `Schedule.kind`; idempotent `kind TEXT NOT NULL DEFAULT 'task'` column in `ensure_schedule_tables` (create-table + ALTER additions); kind read/validate in `_row_to_schedule`; `create_schedule(kind=…)`; `list_schedules(kind=…)` filter; `kind` in `_UPDATABLE` + validation; three-way `max_runs` semantics in `update_schedule` |
| `dream/bridge/methods.py` | `schedule_create`/`schedule_list` accept optional validated `kind` (absent → `task`, byte-for-byte P-12 behavior); `kind` passthrough in `schedule_update` fields |
| `apps/desktop/src/lib/bridge/types.ts` | `ScheduleKind` type; `BridgeSchedule.kind?` |
| `apps/desktop/src/lib/bridge/schedule.ts` | `kind` in `ScheduleDraft`; `listSchedulesOfKind()` wrapper |
| `apps/desktop/src/lib/bridge/echo-subagents.ts` | `EchoScheduleRuntime` honors/validates `kind` in create/list/update (mirror of sidecar semantics) |
| `apps/desktop/src/routes/memory.tsx` | Third tab "Reminders", lazy-loaded panel |
| `apps/desktop/src/routes/scheduler.tsx` | Lists `kind='task'` only via `listSchedulesOfKind` |
| `apps/desktop/src/components/memory/reminders-panel.tsx` | **New.** Reminder list + create/edit dialog (once/repeat modes, live server preview, Jalali/Gregorian fire time), pause/resume, run-now, history, delete confirmation |
| `apps/desktop/src/components/memory/reminder-model.ts` | **New.** Deterministic one-off date+time → `M H D Mon *` compile, prefill split, rollover-safe future validation, text bounds, locale-aware prompt prefix |
| `apps/desktop/src/components/memory/reminder-model.test.ts` | **New.** 11 unit tests |
| `apps/desktop/src/components/memory/reminders-panel.test.tsx` | **New.** 11 component tests |
| `apps/desktop/src/routes/memory.test.tsx` | +1 test: reminders tab switch |
| `apps/desktop/src/routes/scheduler.test.tsx` | +1 test: page requests `kind=task`, hides reminders |
| `apps/desktop/src/locales/{en,fa,zh-CN,ja,es,de,fr,ko}/memory.json` | `reminders.*` subtree (50 keys; fa fully translated) |
| `tests/test_p13_reminder_authoring.py` | **New.** 19 backend tests |
| `MASTER_CHECKLIST.md` | §2.3 checked |
| `P-13-SYNTHESIS.md`, `P-13-AUDIT.md` | Phase documents |

### Explicitly out of scope (and untouched)

`dream/reminders.py` (legacy Jalali reminder system: CLI, Tkinter, Telegram,
prompt injection — byte-for-byte unchanged), `dream/memory.py`,
`dream/memory_stores.py`, `dream/cron.py`, `dream/nl_schedule.py`,
`dream/agent.py`, `desktop.py`, `cli.py`, `dream/bridge/server.py`, all
gateway/`remotegw`/Web-Gateway code, `.github/` workflows, release tooling,
all Rust sources (`src-tauri/` — the Rust bridge is method-agnostic framing),
provider routing, billing/quota, SEC-phase implementations, bounded stores,
every other route/component, `CHANGELOG.md` (no v0.4.7), package versions.

## Architecture

### Memory explorer (pre-existing, verified — not modified)

Persian-normalised SQLite+FTS5 store (`dream/memory.py`) behind
`memory.list|search|get|update|delete|count|create` RPCs; cursor pagination
hard-capped at 500/page; `normalize_fa` on write and read; soft-archive
delete by default with truthful "no undo unless…" wording; virtualized list;
timeline grouped day/week/month; per-user row scoping. Audit found no
defects; core memory code was not changed.

### Reminders (new surface, existing engine)

A reminder **is** a schedule of `kind='reminder'`:

```
authoring (Memory ▸ Reminders tab)
   └─ schedule.create {kind:'reminder', …}        ← one-off: cron from date+time, max_runs=1
        └─ SQLite schedules table (kind column, default 'task')
             └─ the ONE SchedulerDaemon (P-12, untouched logic)
                  ├─ 30s poll → due_schedules (kind-agnostic)
                  ├─ claim_due_schedule (atomic, no double-run)
                  ├─ require_approval → fail-closed gate (unchanged)
                  └─ runner(prompt) → ScheduleRun history (unchanged semantics)
```

- **No second engine, no second worker:** the daemon, claim path, approval
  gate, restart recovery (`recover_interrupted_runs`), drain-then-cancel stop
  and history rows are the existing P-12 code; `kind` only labels rows and
  filters lists. Verified by tests: a reminder and a task fire in the *same*
  `tick` pass through one daemon.
- **One-off semantics:** date+time compiles client-side to `M H D Mon *`
  cron + `max_runs=1`; the sidecar re-validates the cron and computes
  `next_run`; after one claim the schedule is `exhausted` and the daemon
  skips it (existing `due_schedules` behavior).
- **Legacy reminders untouched:** `dream/reminders.py` keeps its own
  tables/CLI/Tkinter/Telegram surfaces. This phase adds no bridge to them.

### State machines

Reminder (riding the schedule state machine):

```
create(enabled) ─→ enabled ─ toggle ⇄ paused
   │ next_run = cron.after(now)
   ├ due+claimed (atomic) ─→ [approval gate if set: deny/timeout ─→ approval_denied]
   │                            └ approve ─→ run "running" ─→ success | error
   └ max_runs=1 & run_count≥1 ─→ exhausted (terminal)
delete ─→ row + history cascade (permanent, no recovery)
```

`max_runs` update contract: omitted → preserved; explicit `null` → cleared
(once → repeat); integer ≥1 → set; anything else rejected **before** any
write. Key presence in the kwargs dict is the signal — no plain-`None`
default.

## Privacy & security analysis

- No memory or reminder content is written to logs: new UI code has zero
  `console.*`/storage/URL usage (grep-verified); bridge logging remains the
  SEC Stage C value-scanned pipeline, untouched.
- Search terms and reminder text never enter URL/query state: the tab is
  plain component state; the reminders panel has no router params.
- Delete is confirmation-gated (`ConfirmDialog`, focus-restoring) with
  truthful "removed permanently — there is no undo" wording in all 8 locales.
- Preview calls use `schedule.preview`, which persists nothing.
- Approvals for dangerous scheduled work remain the P-12 fail-closed gate;
  reminders do not bypass it (`test_reminder_approval_gate_fails_closed`).
- Access stays local-user scope; the Web Gateway is untouched.
- Residual (pre-existing, unchanged): `logger.debug("schedule %s failed",
  …, exc_info=True)` can carry prompt text in tracebacks at debug level;
  P-12 behavior, out of scope per the phase rules.

## UI / accessibility / RTL

Reminders tab follows the memory/scheduler patterns: labelled controls,
`role="tab"` semantics, aria-live status, `dir="auto"` on Persian content,
`ltr-island` for cron, dual Gregorian + Jalali fire times (Persian digits,
asserted in tests), status never color-only (badges carry text), destructive
delete behind an accessible dialog with focus restore, skeleton loading,
error+retry, offline banner, empty state, and virtualized rendering
(`VirtualList`, `virtualizeAt=0`). Locale completeness enforced by
`tools/check_locales.py` (fa gate: 0 English fallbacks).

## Verification — exact commands and results (executed)

Backend (Python 3.13, repo `.venv`):

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | `23 failed, 3444 passed, 16 skipped in ~161s` — **failure set byte-identical to the pristine base checkout** (see below) |
| `.venv/bin/python -m ruff check .` | `All checks passed!` |
| `.venv/bin/python -m pytest tests/test_scheduler.py tests/test_bridge_memory_skills.py tests/test_bridge_subagent_schedule.py` (targeted, pre-existing) | `207 passed` (on the unmodified suites) |
| `.venv/bin/python -m pytest tests/test_p13_reminder_authoring.py tests/test_scheduler.py tests/test_bridge_subagent_schedule.py` | `216 passed in 2.12s` |
| `.venv/bin/python -m pytest tests/test_p13_reminder_authoring.py` | `19 passed` |
| `.venv/bin/python tools/check_suite_count.py` | `3472 tests collected (minimum required: 652)` — pass |
| `.venv/bin/python -m mypy dream/scheduler.py` | 0 errors in this file |
| `.venv/bin/python -m mypy dream/bridge/methods.py` | 6 errors — same 6 as the pristine base (pre-existing; none on changed lines); mypy is not CI-gated |

Pre-existing sandbox failures (NOT introduced by P-13; identical list on the
pristine base commit): 23 tests in `tests/test_sec_agentic_audit.py`,
`tests/security/test_sec_surfaces_f.py`,
`tests/security/test_sec_transport_hardening.py` — environment-sensitive
security probes that fail in this offline sandbox. GitHub CI adjudicates.

Frontend (`apps/desktop`, Node/npm):

| Command | Result |
|---|---|
| `npm run typecheck` | pass (`tsc --noEmit`, no output) |
| `npm run lint` | **0 errors**, 13 pre-existing `react-refresh` warnings |
| `npm run format:check` | `All matched files use Prettier code style!` |
| `npm test` | `Test Files 110 passed (110)`, `Tests 751 passed (751)` |
| `npm run build` | `✓ built in 5.51s` |
| `npm run locales:check` (`python tools/check_locales.py`) | `PASS — 8 locales × 30 namespaces; fa=0 fallbacks` |

Rust: no Rust file changed; `cargo fmt/check/test/clippy` run unchanged in
CI (no toolchain in this sandbox — compile verification deferred to CI, same
as prior phases).

### Test matrix (deterministic; no sleeps, no network, synthetic content)

Backend `tests/test_p13_reminder_authoring.py`: kind round-trip/serialise;
kind list filter; kind update; invalid kind rejected before persistence
(create/list/update, row unchanged); legacy-schema migration idempotent +
defaults `task`; once→repeat clears `max_runs`; once→once preserves `1`;
repeat→once sets `1`; omitted preserves; invalid `max_runs` rejected before
persistence; P-12 kwarg-style update backward compatibility; one-off fires
exactly once then exhausts (daemon + forced due, drained); reminder rides
the same single daemon tick as a task; approval gate fail-closed
(`approval_denied`, runner never called); bridge create/list by kind +
default `task`; bridge invalid-kind rejections persist nothing; bridge
three-way `max_runs` (omitted/null/integer over the wire); one-off cron
preview determinism (`upcoming_runs` with fixed `after`).

Frontend: `reminder-model.test.ts` — cron compile, malformed refusal,
round-trip prefill, non-one-off rejection, `isOneOff` shape rule, future
accept / past refuse / rollover-date refuse, text bounds, locale prompt
prefix, trimming. `reminders-panel.test.tsx` — list requests
`kind:'reminder'` only; empty state; one-off create sends
`{cron, max_runs:1, kind}`; Jalali digits on the card; past date refused
(disabled submit, nothing sent); repeat create via rhythm preview;
unparseable rhythm blocked; pause/resume via `schedule.toggle`; delete only
after confirmation with truthful wording; load failure + retry; accessible
labelling; edit once→repeat sends `max_runs:null` and drops the once badge.
Route tests — Memory page tab switching (lazy panel mount/unmount);
Scheduler page sends `kind:'task'` and hides reminders.

### Skipped / not executed here

- The 16 skipped backend tests are the repo's own platform skips (unchanged).
- The 23 security-suite failures listed above did not pass **in this
  sandbox** on the base commit either; they are recorded, not claimed green.
- Rust/cargo not executed locally (no toolchain); CI runs them unchanged.
- The daemon's wall-clock 30s poll loop is not exercised in real time; tests
  drive `tick()` directly (injectable seam), per repo convention.

## Migration, compatibility, rollback

- `kind` column: idempotent `ALTER TABLE … ADD COLUMN kind TEXT NOT NULL
  DEFAULT 'task'` inside `ensure_schedule_tables` (same pattern as the P-12
  additions). Pre-existing rows read `task`; legacy callers that omit `kind`
  behave identically to before (covered by the untouched 207-test P-12/P-06
  suites plus the explicit compatibility test). Old clients tolerate the
  extra column.
- Wire shape: `schedule_to_dict` gains `kind`; TypeScript marks it optional
  so older sidecar payloads still typecheck.
- Rollback: revert the commit — the extra column is ignored by the prior
  code path (`_row_to_schedule` guards with `keys()`), no data migration to
  undo.

## Residual risks

1. Pre-existing sandbox security-test failures (above) — environment-bound;
   tracked by CI, not this phase.
2. Cron is machine-local time (P-12 convention): a reminder authored while
   traveling fires at the *machine's* local clock; the UI shows both
   Gregorian and Jalali renderings of that same moment.
3. `oneOffParts` prefill infers the year (cron has none) — next occurrence
   of the compiled month/day; the preview always shows the real next fire.
4. Reminder text is stored as the schedule `name` (and inside the derived
   prompt), so it appears in schedule listings returned by `schedule.list`
   to the same local user — same trust boundary as every other schedule.

## CI

- Local commit: `f623b47` (`feat(memory): add reminder authoring on the
  existing scheduler (P-13)`) on branch `arena/01a0734c-dream`, based on
  `0b5617c0d444501644559c35f11030c9526760f4`. Working tree clean.
- **Status at audit time:** the push and PR creation are blocked — `git push`
  and `gh` both fail with GitHub authentication errors from this sandbox
  (`could not read Username`, `HTTP 401 Bad credentials`). The GitHub
  connection needs to be re-authorised; the push + PR will follow in the
  same session once it is. The final remote SHA and its CI results will be
  appended here and to the PR after that happens.
- CI matrix that will adjudicate: Python 3.10–3.13
  (pytest/ruff/commit-rules/suite-count) + desktop job
  (typecheck/lint/format/test/build/performance/accessibility/locales) +
  Rust job (fmt/clippy/build/test; no Rust sources changed).
- Note on commit rules: `tools/check_commit.py` flags the platform-injected
  `Co-authored-by` attribution trailer (the same trailer and bot author
  appear on the merged main HEAD `0b5617c` from PR #126, which passed CI).
  The commit author itself is `Ali Naderi <alinaderi@users.noreply.github.com>`
  exactly as the rules require.
- The PR will stay **open and unmerged**; no release tag, no v0.4.7.
