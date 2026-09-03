# SEC-06 — Interruptible Sleep & Cancellation Audit

Base commit: `11cd5bc3f31643b10a52d0ff7d49bf85b37ff61c` (SEC-05)
Working branch: `arena/01a065fa-dream` (this session is fixed to this branch by the Arena environment).

Target release: v0.4.7 (repository version remains 0.4.6 in `pyproject.toml`; versioning update is outside SEC-06 scope).

## 1. Sleep-site inventory

Inventory was taken before editing. Production results only; test sleeps are out of scope.

### Scoped production sites (17 call sites + 1 injectable default)

| File | Before | Duration | Cancellation source |
|---|---|---:|---|
| `dream/agent.py` | `time.sleep(...)` | `retry_backoff_seconds * 2**attempt` | none today → helper with `cancel=None` |
| `dream/telegram.py` | `self._sleep(delay)` | `_poll_backoff(failures)` | `_stopping` `threading.Event` |
| `dream/acp/client.py` | `asyncio.sleep(0.01)` | 0.01 | none today → `cancel=None` |
| `dream/bridge/methods.py` | `asyncio.sleep(0.05)` | 0.05 | none today → `cancel=None` |
| `dream/bridge/methods_research.py` | `asyncio.sleep(0.05)` | `_STREAM_POLL_SECONDS` | none today → `cancel=None` |
| `dream/connectivity/adapters/telegram.py` | 2× `asyncio.sleep(...)` | backoff, `poll_interval` | `_stop_event` `asyncio.Event` |
| `dream/connectivity/adapters/slack.py` | 2× `asyncio.sleep(5.0)` | 5.0 | `_stop_event` `asyncio.Event` |
| `dream/connectivity/adapters/signal.py` | 2× `asyncio.sleep(...)` | 5.0, 0.5 | `_stop_event` `asyncio.Event` |
| `dream/connectivity/adapters/email.py` | 2× `asyncio.sleep(...)` | `_poll_seconds()`, 5.0 | `_stop_event` `asyncio.Event` |
| `dream/connectivity/adapters/discord.py` | 4× `asyncio.sleep(...)` | backoff, 5.0, 1.0, heartbeat interval | `_stop_event` `asyncio.Event` |

`dream/telegram.py` also keeps the constructor's injectable `sleep` seam defaulted to `time.sleep`; the production call goes through `_interruptible_sleep()`, which uses the cooperative helper when the default seam is active and still calls injected callbacks in tests.

### Out-of-scope production sites found but not changed

| File | Sleep | Rationale for leaving |
|---|---|---:|---|
| `dream/session_search.py:369` | `time.sleep(0.05)` | outside SEC-06 scope; `session_search.py` is not in the approved file list |
| `dream/providerhubs/adapters.py:130` | `time.sleep(...)` | outside scope (`providerhubs` adapter not listed) |
| `dream/reliability/db.py:106,120` | `time.sleep(...)` | outside scope (`reliability/db.py` not listed) |
| `dream/reliability/resource.py:109` | injectable `sleep=time.sleep` | outside scope; injection seam, not a direct call |
| `dream/subagents.py:710` | `asyncio.sleep(tick)` | outside scope (`subagents.py` not listed) |
| `dream/bridge/streams.py:115,141` | `asyncio.sleep(delay)` | outside scope (`bridge/streams.py` not listed) |
| `dream/reliability/sleep.py` | helper implementation | required blocking/asynchronous primitive inside the helper |

Total production `time.sleep(` locations inspected: helper, `session_search`, `providerhubs/adapters`, `reliability/db` (2), so 5 blocking calls outside the scoped loop remain (all out-of-scope except the helper). No scoped production file still contains `time.sleep(` or `asyncio.sleep(`.

## 2. Cancellation integration

The project already uses `dream.reliability.cancel.CancelToken` (with `is_cancelled()`, `throw_if_cancelled()`, and `as_event()`). SEC-06 reuses that token and adds one small integration piece:

- `CancelToken.link_async_event(event)` and `CancelToken.from_async_event(event)` wrap an existing `asyncio.Event` stop flag (used by every connectivity adapter) without introducing a second cancellation system.
- `CancelToken.cancel()` and `CancelToken.is_cancelled()` already understood linked `threading.Event`s; they now also handle linked objects that expose `set()`/`is_set()` so an `asyncio.Event` can be both observed and signalled.

## 3. Helper contract

New module: `dream/reliability/sleep.py`.

- `interruptible_sleep(seconds, cancel=None, granularity=0.05) -> None`
- `ainterruptible_sleep(seconds, cancel=None, granularity=0.05) -> None`

Behavior:

- `seconds <= 0` returns immediately.
- `granularity <= 0`, `NaN`, or infinity raises `ValueError`.
- A cancelled token is checked before sleeping and after every bounded slice.
- Synchronous no-token case delegates to `time.sleep` exactly (no drift).
- Synchronous token case waits on `cancel.as_event().wait(slice)`; it never spins and wakes immediately for token cancellation.
- Async helper yields to the loop on each slice using `asyncio.sleep`.
- Token cancellation raises `OperationCancelled` (the project's existing cancellation exception); it does not return early.
- `asyncio.CancelledError` is never converted to a normal return and propagates unchanged.

## 4. Replacements and preserved timing

- `dream/agent.py`: retry delay expression unchanged; `interruptible_sleep(...)` called with `cancel=None` because `OpenAIBackend.chat()` has no token. Duration, retry count, and 429-only retry logic are unchanged.
- `dream/telegram.py`: injected `sleep` callbacks still receive the exact delays in tests; default production path uses `CancelToken.from_research_stop(self._stopping)` and the cooperative helper. Backoff formula unchanged.
- `dream/connectivity/adapters/*`: all `await asyncio.sleep(...)` replaced with `await ainterruptible_sleep(..., cancel=CancelToken.from_async_event(self._stop_event))`, preserving every duration and retry/jitter expression.
- `dream/acp/client.py`, `dream/bridge/methods.py`, `dream/bridge/methods_research.py`: replaced with the helper, `cancel=None`, durations unchanged.
- No event-driven waits were turned into longer polling intervals; the only polling intervals are the pre-existing ones.

## 5. Tests

New file: `tests/test_reliability_sleep.py` (15 tests). Covers:

- zero/negative durations return promptly;
- pre-start cancellation;
- sync cancellation within granularity;
- async cancellation within granularity;
- no-cancellation completion;
- invalid granularity (sync and async);
- `asyncio.CancelledError` propagation;
- async `asyncio.Event` stop integration;
- sync helper does not use `time.sleep` while a token is supplied;
- agent retry/backoff caller preserves effective durations;
- scoped production files no longer contain `time.sleep(` or `asyncio.sleep(`.

Commands and results:

```text
.venv/bin/python -m pytest -q tests/test_reliability_sleep*.py tests/test_*sleep*.py
15 passed in 0.24s
```

Existing impacted suites:

```text
.venv/bin/python -m pytest -q tests/test_reliability_sleep.py tests/test_reliability.py \
  tests/test_connectivity_adapters.py tests/test_telegram.py
93 passed in 2.25s

.venv/bin/python -m pytest -q tests/test_bridge_methods.py tests/test_acp.py tests/test_connectivity_bridge.py
36 passed in 0.95s
```

Full suite:

```text
.venv/bin/python -m pytest -q
3070 passed, 14 skipped in 102.91s (0:01:42)
```

## 6. Idle-behavior measurement

Method: one-second synthetic polling wait, measuring wall time and process CPU time. The "old" style is the direct `time.sleep(min(remaining, 0.05))` / `asyncio.sleep(min(remaining, 0.05))` loop; the "new" style is the SEC-06 helper with `CancelToken` and `granularity=0.05`.

```text
sync-old: wall=1.000s cpu=0.0009s
sync-new: wall=1.000s cpu=0.0014s
async-old: wall=1.001s cpu=0.0021s
async-new: wall=1.001s cpu=0.0019s
```

Both forms are almost entirely event/OS-wait bound. There is no claim of a CPU reduction; the measurement shows idle wall-time compatibility and no busy-spin regression.

## 7. Remaining intentional sleeps

- `dream/reliability/sleep.py`: the synchronous and asynchronous primitives themselves are the only allowed direct sleep calls.
- `dream/session_search.py`, `dream/providerhubs/adapters.py`, `dream/reliability/db.py`, `dream/reliability/resource.py`, `dream/subagents.py`, `dream/bridge/streams.py`: all are outside the strict SEC-06 file list and remain documented as coordination items for a future scope.

No `asyncio.sleep(0.01)` or `asyncio.sleep(0.05)` remains in `dream/`.

## 8. Coordination items

- `OpenAIBackend.chat()` has no cancellation token; wire one in a future owner-facing backend change.
- `ACPClient.stream_message()` has no token; streaming owner should wire one in a future scope.
- Bridge approval gate and research follow-mode have no per-session token at the helper call site; they preserve the 50 ms cadence and can be wired when those sessions expose a `CancelToken`.

## 9. Verification commands

```text
.venv/bin/ruff check dream/reliability dream/agent.py dream/connectivity dream/telegram.py \
  dream/acp/client.py dream/bridge/methods.py dream/bridge/methods_research.py tests/
All checks passed!

.venv/bin/python -m pytest -q
3070 passed, 14 skipped in 102.91s (0:01:42)

.venv/bin/python tools/check_suite_count.py
Suite count check passed: 3073 tests collected (minimum required: 652).

rg -n "time\.sleep\(" dream
dream/session_search.py:369: ...
dream/reliability/sleep.py:75: ...
dream/reliability/db.py:106,120: ...
dream/providerhubs/adapters.py:130: ...

rg -n "asyncio\.sleep\((0\.01|0\.05)" dream
(no matches)

git diff --check
(clean)
```

`tools/check_commit.py HEAD` reports failures only for the pre-existing base commit author (`arena-ai-coding-agent[bot]`). The SEC-06 commit is written with the project-required author name/email and is verified after commit.
