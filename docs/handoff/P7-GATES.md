# P7 gate evidence — Reliability, anti-hang & engine resilience

Date: 2026-08-25. Base: `5e8c7fc7f9813d811cda9c5df03e579fd75529c5`
(`feat(security): agentic defense-in-depth for code exec, plans, claims, and
gateways (#89)` — P6 merged).
**New commit: `e1a7d4082241cd5d4af9a2652e334080d4d31715`**
(`feat(reliability): timeouts, cancellation, watchdog, and graceful
degradation`), authored `Ali Naderi <alinaderi@users.noreply.github.com>`.
`python tools/check_commit.py` →
`Commit author and trailer rules passed for HEAD!`
Python 3.11.2, ruff 0.16.4, pytest 9.1.1.

All output below is real, copied from the runs described. Live-provider
smoke is owner-run and is not claimed here.

## Summary

| Gate | Command | Observed result |
|---|---|---|
| Definition-of-done 1 — async + subprocess cancel | `pytest tests/test_reliability_process.py -q` | **PASS** — 9 passed, including `test_async_and_subprocess_cancel_together` |
| Definition-of-done 2 — hung task reaped + soak | `pytest …::test_watchdog_reaps_hung_thread_and_records_cause` · `python tools/soak_test.py` | **PASS** — watchdog records cause; `SOAK PASS rounds=59 elapsed=25.12s` |
| Definition-of-done 3 — budgets EN+FA | `pytest tests/test_reliability.py -q -k budget` | **PASS** — bilingual exhaustion text |
| Definition-of-done 4 — stalled producer | `pytest tests/test_reliability_streams.py -q` | **PASS** — 8 passed, `StreamStalledError` not an infinite generator |
| Definition-of-done 5 — two-process SQLite | `pytest tests/test_reliability_db.py -q` | **PASS** — 6 passed, zero `database is locked`, one claim winner |
| Definition-of-done 6 — leak test | `pytest tests/test_reliability_leaks.py -W error::ResourceWarning -q` | **PASS** — 2 passed |
| Definition-of-done 7 — lint | `python -m ruff check .` | **PASS** — `All checks passed!` (exit 0) |
| Definition-of-done 7 — full suite, zero regressions | `python -m pytest -q` | **PASS** — 2908 passed, 14 skipped (baseline 2851 passed, 14 skipped) |
| Suite count | `python tools/check_suite_count.py` | **PASS** — 2911 tests collected (minimum 652) |
| Offline demo | `python examples/reliability_demo.py` | **PASS** — exit 0 |

---

## Gate 1 — `ruff check .`

```
$ python -m ruff check .
All checks passed!
$ echo $?
0
```

## Gate 2 — full suite, zero regressions

Baseline, measured on this tree **before** any P7 file existed
(P6 #89 at `5e8c7fc`, after the editable install):

```
$ python -m pytest -q
2851 passed, 14 skipped
```

After P7:

```
$ python -m pytest -q
........................................................................ [  2%]
........................................................................ [ 98%]
...............................                                          [100%]
2908 passed, 14 skipped in 113.77s (0:01:53)
$ echo $?
0
```

**+57 tests, 0 failures, 0 new skips.** The 14 skips are the pre-existing
platform-conditional ones and are unchanged.

```
$ python tools/check_suite_count.py
Suite count check passed: 2911 tests collected (minimum required: 652).
```

## Gate 3 — the new suites individually

```
$ python -m pytest tests/test_reliability.py -q
25 passed in 0.74s

$ python -m pytest tests/test_reliability_process.py -q
9 passed in 7.28s

$ python -m pytest tests/test_reliability_streams.py -q
8 passed in 1.15s

$ python -m pytest tests/test_reliability_db.py -q
6 passed in 0.43s

$ python -m pytest tests/test_reliability_leaks.py -q
2 passed in 0.15s

$ python -m pytest tests/test_reliability_integration.py -q
7 passed in 0.29s
```

Combined:

```
$ python -m pytest tests/test_reliability*.py -q
.........................................................                [100%]
57 passed in 9.46s
```

## Gate 4 — leak test under `-W error::ResourceWarning`

```
$ python -m pytest tests/test_reliability_leaks.py -W error::ResourceWarning -q
..                                                                       [100%]
2 passed in 0.25s
$ echo $?
0
```

## Gate 5 — soak (self-terminating, ≤30 s wall)

```
$ python tools/soak_test.py
SOAK PASS rounds=59 elapsed=25.12s counts={'cancel': 59, 'watchdog': 59, 'budget': 59, 'buffer': 59, 'stream': 59, 'db': 59, 'supervisor': 59} ladder=reduced
$ echo $?
0
```

`SIGALRM` is armed at 30 s. The soft cap is 25 s. The process exited on
its own; it was not killed.

## Gate 6 — offline demo

```
$ python examples/reliability_demo.py
reliability demo
=== cancel ===
adapted P4 token cancelled True linked token
=== deadline / watchdog ===
clamped client delay 2.0
reaped True cause watchdog reaped hung task owner=demo step=hang
owner demo step hang
=== budget ===
Token budget exhausted (used 2 of 2) for demo/reply; this step was refused.
بودجهٔ توکن تمام شد. (2 از 2) demo/reply؛ اجرا نشد.
=== backpressure ===
bounded [{'n': 3}, {'n': 4}, {'n': 5}] dropped 3
=== stream stall ===
stalled demo idle=0.20s
=== sqlite helpers ===
counter 3
claim first True claim again False
durable ok
=== supervisor ===
reaped ['idle']
=== degrade ladder ===
Degraded to offline echo: no provider call will be made.
به حالت پژواک آفلاین رفت: هیچ درخواستی به ارائه‌دهنده فرستاده نمی‌شود.
demo done
```

## Gate 7 — forbidden surface untouched

```
$ git diff --stat -- dream/agent.py dream/subagents.py dream/reminders.py \
    dream/memory_stores.py dream/security dream/research dream/dataqa \
    dream/workspace dream/agentmodes dream/providerhubs cli.py \
    docs/bridge tools/security_audit.py
(no output)
```

The only existing product file edited is `dream/bridge/streams.py`
(additive: `delay` is clamped, `stall_timeout` is opt-in,
`stream_with_stall_guard` / `StreamStalledError` are new names).
`pyproject.toml` gained one E402 per-file-ignore for `tools/soak_test.py`;
the existing `memory_probe` / `runtime_probe` / `sec_agentic_probe` /
`runtime_demo` lines are unchanged.

---

## Definition-of-done matrix

1. **A running async + subprocess operation cancelled by the new token
   within the deadline.**
   `test_cancel_real_subprocess_within_deadline`,
   `test_cancel_async_operation_within_deadline`, and
   `test_async_and_subprocess_cancel_together` use a real
   `subprocess.Popen([sys.executable, "-c", "time.sleep(30)"])` and an
   asyncio loop. One `CancelToken` terminates both inside the deadline.
   **PASS.**

2. **A deliberately hung task is reaped by the watchdog and reported;
   bounded soak passes.**
   `test_watchdog_reaps_hung_thread_and_records_cause` sleeps 45 s
   against a 0.2 s deadline; `watchdog.reaped` is true and `cause`
   names `owner=engine step=model-call`. Soak: 59 rounds in 25.12 s,
   exit 0. **PASS.**

3. **Budgets enforced; exhaustion degrades with honest EN+FA text.**
   Token, time, output-truncate, skip-with-rationale, and ledger-quota
   mapping all raise `BudgetExceeded.bilingual()` containing both
   English and Persian. Demo stdout shows the FA sentence verbatim.
   **PASS.**

4. **A stalled producer yields `StreamStalledError`, not an infinite
   generator.**
   `guarded_aiter` keeps one pending `__anext__`. A 30 s silent
   producer raises after 0.2 s. A mid-stream 0.15 s pause still
   delivers both items. **PASS.**

5. **Two-process DB barrier: zero `database is locked`; idempotent
   per-destination helper proven.**
   Two children increment a counter 40 times each; combined stdout/err
   contains no `database is locked`; final count is 80. Two children
   `claim_delivery` the same row: exactly one `won`, one `dup`.
   `PRAGMA busy_timeout` is 1234 and `journal_mode` is `wal`.
   **PASS.**

6. **Leak test under `-W error::ResourceWarning`.**
   Supervisor + Popen + SQLite + durable write, then `gc.collect()`.
   2 passed. **PASS.**

7. **`ruff check .` clean; full pytest green vs current main; real
   stdout recorded.**
   2908 passed, 14 skipped (was 2851 / 14). This document.
   **PASS.**

## Change surface actually touched

New: `dream/reliability/{__init__,cancel,deadline,budget,backpressure,streams,resource,db}.py`;
`tests/test_reliability.py`, `test_reliability_process.py`,
`test_reliability_streams.py`, `test_reliability_db.py`,
`test_reliability_leaks.py`, `test_reliability_integration.py`;
`examples/reliability_demo.py`; `tools/soak_test.py`;
`docs/architecture/reliability.md`,
`docs/dev/how-to/add-a-reliability-sla.md`,
`docs/handoff/P7.md`, `docs/handoff/P7-GATES.md`.

Extended: `dream/bridge/streams.py` (additive only),
`pyproject.toml` (one E402 entry for the soak tool).

Verified untouched: `dream/agent.py`, `dream/subagents.py`,
`dream/reminders.py`, `dream/memory_stores.py`, `dream/security/**`,
`tools/security_audit.py`, `dream/research/**`, `dream/dataqa/**`,
`dream/workspace/**`, `dream/agentmodes/**`, `dream/providerhubs/**`,
`dream/bridge/methods.py`, `dream/bridge/server.py`, `cli.py`,
`docs/bridge/protocol.md`, `.github/workflows/*`.

## Owner-run, not claimed here

- Live-provider smoke: cancel a real model stream mid-token.
- Wiring the opt-in call sites listed in `P7.md` (research, subagents,
  reminders, memory stores, bridge `_run_streaming`).
