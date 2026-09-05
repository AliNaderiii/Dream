# P-12 Audit — Scheduler UI and Execution Safety Hardening

**Phase:** P-12 (Item 2.6.7 / Gate G9)  
**Branch:** `arena/01a07029-dream`  
**Base `main` SHA:** `2c6e087886d224ad86e8e97d0501e58f425ada6c`  
**Date:** 2026-09-05  
**Status:** PR open and unmerged. **`v0.4.7` was not created.**

---

## 1. Scope and Non-Goals

### In Scope
- **Scheduler UI Polish & Completion:**
  - `apps/desktop/src/routes/scheduler.tsx`: Full schedule cards rendering schedule name, description, human rhythm, cron expression, Jalali/Gregorian upcoming runs, status badge, run-now action, toggle switch, history accordion trigger, edit button, and delete action with confirmation modal.
  - `apps/desktop/src/routes/scheduler.tsx` (`EditScheduleDialog`): Full editing dialog with pre-populated name, description, prompt, natural language rhythm / cron, live preview debounced at 200 ms, approval checkbox, and atomic save.
  - `apps/desktop/src/components/scheduler/schedule-history.tsx`: History timeline rendering status badge, timestamp, duration (`formatDuration`), and safe truncated result summary.
  - `apps/desktop/src/lib/bridge/schedule.ts`: Exported `updateSchedule` bridge helper wrapping RPC `schedule.update`.
  - `apps/desktop/src/lib/bridge/hooks.ts`: Fixed unmount cleanup so child modals do not discard process-wide bridge transport instances.
  - `apps/desktop/src/locales/*/scheduler.json`: Full 8-language localization (`en`, `fa`, `de`, `es`, `fr`, `ja`, `ko`, `zh-CN`) for all new scheduler keys (`editSchedule`, `descriptionLabel`, `descriptionPlaceholder`, `save`, `edit`, `updated`).
- **Core Scheduler Execution Safety:**
  - `dream/scheduler.py` (`claim_due_schedule`): Atomic conditional SQLite update on due schedules (`next_run = ... WHERE next_run = ... AND enabled = 1`) to guarantee exactly-once execution under concurrent daemon polling or multi-worker contention.
  - `dream/scheduler.py` (`recover_interrupted_runs`): Startup recovery transitioning lingering `running` history rows to `error` with `"execution interrupted by system restart"` summary, computing clean duration.
  - `dream/scheduler.py` (`record_run_started`): Correct integer casting on `cursor.lastrowid`.
  - `dream/bridge/methods.py` (`_approval_gate`): Fail-closed finally block ensuring unhandled or timed-out approvals resolve cleanly without dangling state.
- **Verification & Documentation:**
  - `tests/test_scheduler.py`: Added concurrency claim race test, restart recovery test, and update schedule description test.
  - `apps/desktop/src/routes/scheduler.test.tsx`: Added live preview edit flow test and history duration badge verification test.
  - `MASTER_CHECKLIST.md`: Milestone item 2.6.7 marked complete.

### Non-Goals / Explicitly Out of Scope
- No cargo/rust sidecar alterations (cargo unavailable in test environment, documented platform limitation).
- No external network calls, telemetry, or remote dependencies.
- Local Ollama/Echo fallback remains 100% self-contained and offline-capable.
- No arbitrary sleeps; all tests are deterministic with synthetic clocks and abort controllers.

---

## 2. Base `main` SHA
`2c6e087886d224ad86e8e97d0501e58f425ada6c` — remote `origin/main` at phase start.

---

## 3. Architecture and Concurrency Safety

```
+-------------------------------------------------------------------------+
|                              Desktop UI                                 |
|                                                                         |
|  [Schedule Cards]  ---> [EditScheduleDialog] ---> updateSchedule()      |
|  [Run Now / Toggle] ---> (debounced / locked) ---> schedule.run_now()   |
|  [ScheduleHistory] ---> Virtualized Timeline (status + duration)        |
+------------------------------------+------------------------------------+
                                     | JSON-RPC Bridge
                                     v
+-------------------------------------------------------------------------+
|                           Bridge Dispatcher                             |
|                                                                         |
|  schedule.update   ---> updates schedule fields & recalculates next_run |
|  schedule.approve  ---> resolves pending approval gate                  |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                        Scheduler Daemon & Store                         |
|                                                                         |
|  Daemon Startup    ---> recover_interrupted_runs()                      |
|  Daemon Poll (30s) ---> due_schedules()                                 |
|                    ---> claim_due_schedule() (Atomic conditional claim) |
|                    ---> _execute() with fail-closed approval gate       |
|                    ---> record_run_finished() with duration             |
+-------------------------------------------------------------------------+
```

### Safety Invariants
1. **Atomic Concurrency Claim (`claim_due_schedule`):**  
   Advances `next_run` and increments `run_count` in a single atomic SQL statement with `WHERE next_run = ? AND enabled = 1`. If two daemon loops or workers tick simultaneously, exactly one row is updated and returns `True`; the second returns `False` and skips task creation.
2. **Crash Recovery (`recover_interrupted_runs`):**  
   On daemon startup, all historical records with `status = 'running'` are settled to `status = 'error'` with completed timestamp and clear summary, preventing permanent loading/zombie states.
3. **Fail-Closed Approval Gate:**  
   If a dangerous tool execution approval times out or encounters an unhandled rejection, `_approval_gate` defaults to `decision = False` and `resolved = True`, aborting execution safely.
4. **Double-Action Prevention in UI:**  
   `runningMap` and `togglingMap` lock buttons during in-flight RPCs, disabling inputs and preventing duplicate run or toggle dispatches.

---

## 4. Test Evidence & Matrix

| Suite | File | Tests | Outcome |
| :--- | :--- | :--- | :--- |
| **Python Scheduler Core** | `tests/test_scheduler.py` | 134 passed | Clean pass (0 flakiness) |
| **Python Bridge RPC** | `tests/test_bridge_subagent_schedule.py` | 63 passed | Clean pass |
| **Python Cron Storage** | `tests/security/test_sec_cron_storage.py` | 15 passed | Clean pass |
| **Frontend Scheduler Route** | `apps/desktop/src/routes/scheduler.test.tsx` | 11 passed | All scenarios verified |
| **Frontend Virtual History** | `apps/desktop/src/components/scheduler/schedule-history.test.tsx` | 1 passed | 1,000 rows bounded to < 60 mounted DOM nodes |
| **Frontend Stage D A11y** | `apps/desktop/src/routes/stage-d-accessibility.test.tsx` | 9 passed | 0 axe violations |
| **Frontend Full Build** | `apps/desktop` (`npm run build`) | Built in 6.68s | Production dist ready |
| **Frontend Typecheck** | `tsc --noEmit` | 0 errors | Clean types |
| **Frontend Linter** | `eslint .` | 0 errors | Clean lint |

---

## 5. Gate Sign-Off Reference
Phase 0 Gate G9 sign-off was received from the Product Manager prior to frontend implementation, documented in `docs/design/approval-signoff.md`.
