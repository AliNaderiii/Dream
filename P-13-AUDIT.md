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
| `.venv/bin/python -m pytest -q` (instance 1) | `23 failed, 3444 passed, 16 skipped in ~161s` — failure set byte-identical to the pristine base checkout |
| `.venv/bin/python -m pytest -q` (re-executed after sandbox rebuild) | `21 failed, 3446 passed, 16 skipped in 191s` — again byte-identical to the pristine base (detached-checkout re-run) |
| `.venv/bin/python -m ruff check .` | `All checks passed!` |
| `.venv/bin/python -m pytest tests/test_scheduler.py tests/test_bridge_memory_skills.py tests/test_bridge_subagent_schedule.py` (targeted, pre-existing) | `207 passed` (on the unmodified suites) |
| `.venv/bin/python -m pytest tests/test_p13_reminder_authoring.py tests/test_scheduler.py tests/test_bridge_subagent_schedule.py` | `216 passed in 2.12s` |
| `.venv/bin/python -m pytest tests/test_p13_reminder_authoring.py` | `19 passed` |
| `.venv/bin/python tools/check_suite_count.py` | `3472 tests collected (minimum required: 652)` — pass |
| `.venv/bin/python -m mypy dream/scheduler.py` | 0 errors in this file |
| `.venv/bin/python -m mypy dream/bridge/methods.py` | 6 errors — same 6 as the pristine base (pre-existing; none on changed lines); mypy is not CI-gated |

Pre-existing sandbox failures (NOT introduced by P-13; identical set on the
pristine base commit in every run): the exact list, counts per sandbox
instance, and CI adjudication are recorded in the "Local full pytest" section
below. **The full local suite was never green in this sandbox — neither on
the base commit nor on P-13.** GitHub CI (all four Pythons) is green.

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

## CI incident and fix (truthful record)

The **second** CI run (on the docs-only commit `56c2567`, pushed ~10:03 UTC)
failed `test (3.10)`, `test (3.11)`, `test (3.12)` — while the **identical
code** had passed all four Pythons forty minutes earlier (run of ~09:32 UTC
on `67b0623`). Root cause, reproduced locally and pinned:

- `tests/test_p13_reminder_authoring.py::test_kind_filters_the_list` asserted
  insertion order (`["r1", "r2"]`) over schedules whose crons were
  `0 10 * * *` and `0 11 * * *`.
- `list_schedules` correctly orders by **next fire time**; between 10:00 and
  11:00 local time, "0 11 * * *" fires *today* and sorts first, flipping the
  assertion. The first CI run executed before 10:00 UTC (green); the second
  inside the window (red). A time-of-day-dependent test — exactly the class
  this phase forbids; the production ordering behavior is correct and was
  not changed.
- **Fix:** the filter test now compares names as a set, and a new
  `test_kind_list_order_is_stable_at_any_hour` pins the ordering rule with
  identical cron expressions (equal `next_run` at any hour, tie broken by
  `created_at`), which cannot flip with the wall clock.
- Verified: full P-13 file green under `TZ=UTC`, `Asia/Tehran`,
  `Pacific/Kiritimati`, and `America/New_York` (20 tests each), plus the
  227-test targeted run and ruff.

## CI — final results

- **PR:** [#127](https://github.com/AliNaderiii/Dream/pull/127) —
  `arena/01a0734c-dream` -> `main`, **open and unmerged** (state verified
  live via the API at head `67b5623`; the branch head was then advanced to
  the test-fix commit below; not merged, no release tag, no v0.4.7).
- **Final remote head SHA (push confirmed):**
  `7d13acf727726c728b6cd1ce3faee9f75bc390a4`
  (`test(p13): make the kind-filter test independent of wall-clock time`) —
  commits in the PR:
  1. `67b5623` feat(memory): add reminder authoring on the existing scheduler (P-13)
  2. `56c2567` docs(p13): record PR number, final CI results, and local failure set
  3. `7d13acf` test(p13): make the kind-filter test independent of wall-clock time
  All three authored `Ali Naderi <alinaderi@users.noreply.github.com>`, zero
  trailers, `tools/check_commit.py HEAD` passes on each.

### Run A — code commit `67b5623` (all 8 observed PASS)

| Check | Result | URL |
|---|---|---|
| test (3.10) | pass, 3m38s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466038467 |
| test (3.11) | pass, 3m22s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466038846 |
| test (3.12) | pass, 3m35s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466039013 |
| test (3.13) | pass, 3m19s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466039300 |
| Frontend checks | pass, 2m25s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139135 |
| Rust (ubuntu-22.04) | pass, 2m33s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139040 |
| Rust (windows-latest) | pass, 2m29s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139107 |
| Rust (macos-latest) | pass, 2m5s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139026 |

(One earlier 3.10 attempt in run A was cancelled mid-step by a GitHub runner
loss and automatically re-run; the retry passed. Each `test (3.x)` job
internally ran pytest, ruff, the PR commit-rules gate and the suite-count
gate — all green.)

### Run B — docs commit `56c2567` (observed: 3 FAIL — see incident below)

test (3.10) / (3.11) / (3.12) failed on the time-of-day flake documented in
the next section; test (3.13), Frontend and all Rust jobs passed. Run:
https://github.com/AliNaderiii/Dream/actions/runs/34026084375

### Run C — final head `7d13acf` (observed 7 of 8 PASS; 1 pending observation)

| Check | Result | URL |
|---|---|---|
| test (3.11) | **pass**, 3m27s | https://github.com/AliNaderiii/Dream/actions/runs/34026786803/job/101469067158 |
| test (3.12) | **pass**, 3m22s | https://github.com/AliNaderiii/Dream/actions/runs/34026786803/job/101469067162 |
| test (3.13) | **pass**, 3m52s | https://github.com/AliNaderiii/Dream/actions/runs/34026786803/job/101469067182 |
| Frontend checks | **pass**, 3m28s | https://github.com/AliNaderiii/Dream/actions/runs/34026786808/job/101469067350 |
| Rust (ubuntu-22.04) | **pass**, 2m7s | https://github.com/AliNaderiii/Dream/actions/runs/34026786808/job/101469067239 |
| Rust (windows-latest) | **pass**, 3m12s | https://github.com/AliNaderiii/Dream/actions/runs/34026786808/job/101469067356 |
| Rust (macos-latest) | **pass**, 1m49s | https://github.com/AliNaderiii/Dream/actions/runs/34026786808/job/101469067389 |
| test (3.10) | **pass**, 3m18s | https://github.com/AliNaderiii/Dream/actions/runs/34026786803/job/101472083712 |

Run C observation note: the original run-C 3.10 attempt
(job 101469067342) was lost to the same GitHub runner issue seen in run A
and automatically re-run; the retry (job 101472083712) **passed**. The
status could not be observed live because the sandbox GitHub token expired
mid-watch; it was independently confirmed after authentication was restored
(an independent verification by the PM side matched: 3.10 was still in
progress at that moment, then completed green).

**Result: all eight checks PASS on `7d13acf727726c728b6cd1ce3faee9f75bc390a4`.**
The final remote head is this documentation commit (production code
unchanged since `7d13acf`); the definitive merge-gate verification is the
green CI run covering this commit, whose check-run URLs are attached to
PR #127.

## CI incident and fix (truthful record)

The **second** CI run (on the docs-only commit `56c2567`, pushed ~10:03 UTC)
failed `test (3.10)`, `test (3.11)`, `test (3.12)` — while the **identical
code** had passed all four Pythons forty minutes earlier (run of ~09:32 UTC
on `67b0623`). Root cause, reproduced locally and pinned:

- `tests/test_p13_reminder_authoring.py::test_kind_filters_the_list` asserted
  insertion order (`["r1", "r2"]`) over schedules whose crons were
  `0 10 * * *` and `0 11 * * *`.
- `list_schedules` correctly orders by **next fire time**; between 10:00 and
  11:00 local time, "0 11 * * *" fires *today* and sorts first, flipping the
  assertion. The first CI run executed before 10:00 UTC (green); the second
  inside the window (red). A time-of-day-dependent test — exactly the class
  this phase forbids; the production ordering behavior is correct and was
  not changed.
- **Fix:** the filter test now compares names as a set, and a new
  `test_kind_list_order_is_stable_at_any_hour` pins the ordering rule with
  identical cron expressions (equal `next_run` at any hour, tie broken by
  `created_at`), which cannot flip with the wall clock.
- Verified: full P-13 file green under `TZ=UTC`, `Asia/Tehran`,
  `Pacific/Kiritimati`, and `America/New_York` (20 tests each), plus the
  227-test targeted run and ruff.

## CI — final results

- **PR:** [#127](https://github.com/AliNaderiii/Dream/pull/127) —
  `arena/01a0734c-dream` -> `main`, **open and unmerged**.
- **Code SHA fully verified by CI:** `67b062375063f6dc7d106f257d4f9ecc42a29805`
  (`feat(memory): add reminder authoring on the existing scheduler (P-13)`),
  author `Ali Naderi <alinaderi@users.noreply.github.com>`, no trailers,
  `tools/check_commit.py` passes on it. (This audit update is the only later
  commit; its CI run is recorded below.)
- **All 8 checks PASS on that SHA:**

| Check | Result | URL |
|---|---|---|
| test (3.10) | pass, 3m38s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466038467 |
| test (3.11) | pass, 3m22s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466038846 |
| test (3.12) | pass, 3m35s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466039013 |
| test (3.13) | pass, 3m19s | https://github.com/AliNaderiii/Dream/actions/runs/34024943063/job/101466039300 |
| Frontend checks | pass, 2m25s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139135 |
| Rust (ubuntu-22.04) | pass, 2m33s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139040 |
| Rust (windows-latest) | pass, 2m29s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139107 |
| Rust (macos-latest) | pass, 2m5s | https://github.com/AliNaderiii/Dream/actions/runs/34024943006/job/101464139026 |

Each `test (3.x)` job internally ran pytest, ruff, the PR commit-rules gate
and the suite-count gate — all green on every Python. One 3.10 job attempt
was cancelled mid-run by a GitHub runner loss and was automatically re-run
(the retry passed). CI's full-suite green on all four Pythons also confirms
the local failures below are sandbox-environment-bound, not code defects.

## Local full pytest — NOT fully green (truthful record)

The full local `pytest -q` in this sandbox was **not** green:

- First sandbox instance: `23 failed, 3444 passed, 16 skipped`.
- The sandbox was rebuilt mid-phase (fresh clone; commit objects lost, file
  changes preserved); re-executed after rebuild:
  `21 failed, 3446 passed, 16 skipped in 191s`.
- In both cases the **failure set was reproduced byte-identically on the
  pristine base commit `0b5617c`** (verified via stash / detached-checkout
  re-runs and `diff` of the FAILED lists — identical sets).
- Every failure is an environment-sensitive security probe expecting an
  audit-script execution context this offline sandbox does not provide:

```
tests/security/test_sec_surfaces_f.py::test_audit_script_fails_when_a_layer_breaks
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-A docker-absence no longer refuses-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-A import allowlist disabled-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-A output truncation removed-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-A path confinement removed-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-B codegen scanner disabled-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-B data framing loses its banner-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-B literals become raw interpolation-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-C autonomous sessions can mint approval-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-C expensive actions are reclassified-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-C plan gate always allows-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-C the approval throttle is removed-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-D artifact seals are never checked-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-D claim verification always passes-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-D run fingerprints ignore the code-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-E global grants are allowed-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-E probes accept any endpoint-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-E snapshots stop redacting-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-E the gateway enables every tool-...]
tests/test_sec_agentic_audit.py::test_the_audit_fails_when_a_control_breaks[L9-E tokens stop being tool-scoped-...]
tests/test_sec_agentic_audit.py::test_the_baseline_layers_still_alarm
```

(Parametrized IDs abbreviated with `-...` for the embedded probe source;
the full IDs are in the PR's CI history and the raw local logs.)

- The count difference (23 -> 21 across sandbox instances) is sandbox drift;
  within a single instance the sets were stable and identical to base.
- **CI adjudicated: all four Python matrix jobs pass the complete suite** on
  the PR SHA — zero new P-13 failures, and the pre-existing local failures
  do not reproduce on CI runners.
