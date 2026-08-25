# Reliability Architecture — Timeouts, Cancellation, Budgets

> Status: **implemented** · Prompt P7 · Nothing hangs forever.

## 1. Mission

Every blocked path in Dream yields a result, a controlled failure, or a
clear cancelled / timed-out / stalled signal. A spinner is not a result.
A leaked thread, FD, or SQLite lock is not a result.

`dream/reliability/` is a reusable toolkit. It does **not** rewrite
research, reminders, memory stores, subagents, or the agent loop. Those
owners opt in at documented call sites.

## 2. Package layout

```
dream/reliability/
├── __init__.py       # public API + graceful-degradation ladder
├── cancel.py         # CancelToken; adapters for P4 / P1 stop flags
├── deadline.py       # scoped deadlines, clamped waits, Watchdog
├── budget.py         # time/tokens/output/disk/memory/money + EN+FA
├── backpressure.py   # bounded buffers (drop-oldest / coalesce / reject)
├── streams.py        # guarded async iterators, StreamStalledError
├── resource.py       # supervisor: idle reap, 3-restart / 2-5-10s
└── db.py             # busy_timeout-before-WAL, IMMEDIATE, claim_delivery
```

Additive extend: `dream/bridge/streams.py` clamps `delay` and exposes
`stream_with_stall_guard` / `StreamStalledError`. Existing signatures
keep working.

## 3. Invariants

1. **Public waits are capped.** `clamp_delay` / `clamp_timeout` /
   `clamp_wait` refuse `1e9`. Hard maxima: delay 2 s, wait 30 s,
   timeout 120 s, deadline 600 s.
2. **Cancellation is a token, not a UI flag.** `/stop` must fire a
   `CancelToken` that propagates to async tasks, threads, and
   subprocesses.
3. **A hang is reaped.** `Watchdog` cancels the token, records the
   owner/step cause, and raises `DeadlineExceeded`.
4. **A quiet stream terminates.** `guarded_aiter` keeps **one** pending
   `__anext__` task. It never `wait_for`s a fresh `__anext__` (that
   would cancel the generator on every poll). Silence longer than the
   stall limit raises `StreamStalledError`.
5. **Lists stay bounded.** `BoundedBuffer` / `BoundedList` drop, coalesce,
   or reject. The buffer size itself is capped at 10 000.
6. **SQLite does not hang the second process.** `busy_timeout` is set
   **before** `journal_mode=WAL`. Writes use `BEGIN IMMEDIATE` with
   locked-retry backoff.
7. **Fail closed on unknown state.** The degradation ladder ends at an
   honest bilingual error, never at a silent retry loop.

## 4. SLA table

| Surface | Budget | On exhaustion | Owner today |
| --- | --- | --- | --- |
| Plan step delay | 0–2 s (already clamped in P4) | ignore the rest | `dream/agentmodes/plan.py` |
| Research session | `max_time_seconds`, `step_timeout_seconds` | `ResearchTimeout` | `dream/research/session.py` |
| Research section | fair share of the session, floor 30 s | `section.budget_exhausted` | `dream/research/iterate.py` |
| Bridge stream chunk delay | 0–2 s | clamp | `dream/bridge/streams.py` |
| Bridge live producer | stall 5 s (opt-in) | `StreamStalledError` | `dream/bridge/server.py` (opt-in) |
| Commerce turn | plan window (guest 20/day, …) | `QuotaExceeded` → `BudgetExceeded` | `dream/commerce.py` |
| Reminder delivery | one row per `(id, destination, fired_at)` | duplicate is a no-op | `dream/reminders.py` |
| Subagent worker | 3 restarts, backoff 2/5/10 s | mark failed, do not leak | `dream/subagents.py` (opt-in) |
| SQLite write | `busy_timeout` 5 s, 5 retries | raise after retries | memory / reminders / skills |
| Soak / probes | 30 s wall | self-terminate | `tools/soak_test.py` |

## 5. Cancellation and deadlines

```
CancelToken  ──adapt──►  P4 CancellationToken   (dream.agentmodes.cancel)
             ──adapt──►  P1 threading.Event     (RunContext.cancelled)
             ──link───►  subprocess.Popen       (terminate, then kill)
             ──child──►  per-step token

Deadline.after(seconds, owner=…, step=…)
    └── Watchdog(deadline, token).run(fn) / .run_async(coro)
            └── DeadlineExceeded(owner, step) + token.cancel(cause)
```

Adapters wrap existing tokens. They do not replace them. A P4
`cancel()` is visible to a `CancelToken` on the next `is_cancelled()`
poll; a `CancelToken.cancel()` calls the P4 `cancel()` immediately.

## 6. Graceful degradation ladder

```
full  →  reduced  →  offline/echo  →  honest error
```

| Rung | Meaning | EN | FA (gloss) |
| --- | --- | --- | --- |
| `full` | Every capability is available | Running at full capability. | در حال اجرا با توان کامل. |
| `reduced` | Skip expensive work (long runs, extra tools) | Degraded to reduced mode: expensive work is skipped. | به حالت کاهش‌یافته رفت: کار پرهزینه رد می‌شود. |
| `offline_echo` | Do not call a provider; echo or local-only | Degraded to offline echo: no provider call will be made. | به حالت پژواک آفلاین رفت: هیچ درخواستی به ارائه‌دهنده فرستاده نمی‌شود. |
| `honest_error` | Stop and say so | Stopped with an honest error: the engine cannot continue safely. | با خطای صادقانه متوقف شد: موتور نمی‌تواند ایمن ادامه دهد. |

Every step is logged in both languages (`Degradation.step_down`). Owners
must not invent a fifth silent rung.

## 7. Stream integrity

`guarded_aiter` is the only supported way to bound an async producer:

1. Create **one** `asyncio.ensure_future(source.__anext__())`.
2. `asyncio.wait({pending}, timeout=…)` — the task is **not** cancelled
   on a poll timeout.
3. On a real item, drop the completed task and create the next one.
4. On stall / cancel / deadline, cancel that single pending task and
   raise. The UI shows restart, not a spinner.

`dream.bridge.streams.stream_with_stall_guard` is the additive opt-in
for the sidecar. Default `stream_chunks` / `stream_text` behaviour is
unchanged except that `delay` is now clamped.

## 8. Database helpers

```python
conn = connect_sqlite(path)          # PRAGMA busy_timeout, then WAL
run_transaction(conn, fn)            # BEGIN IMMEDIATE + locked retry
claim_delivery(conn, reminder_id=…, destination=…, fired_at=…)
durable_write(path, payload)         # tmp + fsync + os.replace
```

`claim_delivery` is the per-destination idempotency helper modelled on
`check_due_reminders`. Reminders.py is not edited; the helper is ready
for that owner to call.

## 9. Worker hygiene

`ResourceSupervisor` tracks threads and subprocesses.

- `touch(name)` is the heartbeat.
- `reap_stale()` terminates workers idle longer than `idle_timeout`.
- `restart(name)` uses the sidecar policy: at most **3** restarts,
  backoff **2 s, 5 s, 10 s** (injectable in tests).
- `shutdown()` cancels the supervisor token, SIGTERM then SIGKILL,
  joins threads, and drops references so FDs can close.

## 10. Testing

`tests/test_reliability*.py` prove the toolkit with **real** processes
and threads, not only mocks:

- a live subprocess + async loop cancelled by one token inside the deadline
- a hung thread reaped by the watchdog, cause recorded
- budget exhaustion with bilingual EN+FA text
- a stalled producer raising `StreamStalledError`
- two-process SQLite barrier with zero `database is locked`
- per-destination claim: exactly one winner
- leak test under `-W error::ResourceWarning`
- M16: no `assert` inside `if` in this suite

`tools/soak_test.py` loops the same paths and **self-terminates** within
30 seconds (`SIGALRM` + monotonic cap).
