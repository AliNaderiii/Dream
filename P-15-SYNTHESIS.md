# P-15 Synthesis Report — Subagent Monitor & Execution Observability

> Status: **awaiting PM approval**. No production file has been edited. This
> report is the synthesis-gate artifact required before implementation
> (checklist item 3.2, the only unchecked item of Phase 3).

- Base main SHA: `fb45ad8da8270c023acf8e24c293ace1a10cf066`
  (`feat(projects): harden the projects dashboard and workspace isolation (P-14) (#128)`)
- PR #128 is **MERGED** (merge commit == base SHA) and every post-merge check
  is green: CI `test (3.10–3.13)` pass, Desktop CI (Frontend + Rust on
  ubuntu/macos/windows) pass.
- Working branch `arena/01a07728-dream` is clean and identical to
  `origin/main` at that SHA (verified via `git fetch` + `git status`).
- Tags end at `v0.4.6`; **no `v0.4.7` exists and none will be created.**
- Verified baselines on this checkout (all executed, none assumed):
  - `python -m pytest -q` → **3505 passed, 16 skipped**
  - targeted: `test_subagents.py + test_council.py + test_bridge_subagent_schedule.py` → **131 passed**
  - `npm run test` (apps/desktop) → **761 passed (110 files)**
  - `tools/check_locales.py` → PASS (8 locales × 30 namespaces, fa gate PASS)

---

## 1. Existing behaviour (read-only audit)

### 1.1 Backend engine — `dream/subagents.py` (827 lines)

- `SubAgentManager` runs children as asyncio Tasks on the sidecar loop;
  `build_child_tools` snapshots/restores the global tool `REGISTRY` under
  `REGISTRY_LOCK`; each child gets an ephemeral `MemoryStore(":memory:")`,
  a private tool table (dangerous tools dropped even when granted; parent's
  instance-bound closures never leak), a detached ledger, and an
  `ApprovalPolicy` with **no approver** — granted-dangerous stays fail-closed.
- Statuses form a closed set; `paused` only from `running`; terminal states
  freeze `elapsed`; `progress` = max of turns/tokens/duration ratios.
- Budgets: per-child `max_turns` / `max_tokens` (estimator-based, provider-
  independent) / `max_duration` (active wall clock, pause-excluded, enforced
  by a watchdog even mid-provider-call). Concurrency: `max_concurrent = 8`
  on `spawn` (RESOURCE_EXHAUSTED via `ResourceWarning`).
- Pipelines: `spawn_pipeline` chains stage results into the next stage's
  context; a failed/cancelled stage skips the rest; a council is exactly one
  3-stage pipeline (proposer→critic→judge) with default grant only.
- `cancel` waits (grace, default 2 s) then escalates to `Task.cancel()`;
  idempotent on terminal. `cancel_all` signals everything first, then drains,
  then cancels pipeline driver tasks. Bridge `shutdown` calls `cancel_all`.
- `follow_logs` replays recorded history, then subscribes a
  `Queue(maxsize=256)`; `_close_subscribers` pushes a `None` sentinel.

### 1.2 Bridge surface — `dream/bridge/methods.py` §subagent.*/council.*

- 9 `subagent.*` methods + `council.run/get`. Validation today: prompt
  non-empty string; tools an array of strings; `max_*` positive
  (`_positive_int/_positive_float`, **no upper bound**); stages a non-empty
  array of objects; unknown/missing ids → `invalid_params`; pause/resume on
  wrong state → explicit `invalid_params`; concurrency → RESOURCE_EXHAUSTED.
- `subagent.logs` returns a `Stream`; the server emits
  `stream.start/chunk/end` then the final result; errors are redacted by
  `serialise_error` (`redact_text`).
- Provenance: `subagent_spawn`/`subagent_result` exist in the sealed event
  vocabulary; **the bridge subagent handlers do not write provenance records
  today**, and the record format is untouched by this phase.

### 1.3 Frontend — `routes/subagents.tsx` + components

- Collapsible virtualised roster (500 ms poll only while non-terminal work
  exists), detail pane seeded by `subagent.get`, log via `subagent.logs`
  stream (replay-from-start), `SubagentLogTail` renders through `VirtualList`
  (DOM bounded, verified by an existing test at 1 000 rows).
- Selection is derived: falls back deterministically to the newest child.
- AbortController per selection; `liveRef` guards post-unmount setState.
- Spawn dialog (stage list, tool grant chips with `aria-pressed`, numeric
  limits), council dialog/widget; stage-D a11y (axe) and offline suites
  include this route; RTL handled via logical properties + `ltr-island`.
- Echo transport (`echo-subagents.ts`) mirrors the wire contract for
  dev/vitest: same statuses, pipeline chaining, council order, log stream.

### 1.4 Scope isolation (P-12/P-13/P-14 relationships)

- A subagent's only link to a session is the **inert string**
  `parent_session_id` used for list filtering; children never receive the
  parent store, session history, project overlay, or workspace roots.
  Project state cannot leak into a child: verified by
  `test_child_memory_writes_never_reach_the_parent_store`,
  `test_two_subagents_do_not_share_a_store`,
  `test_global_registry_is_unchanged_by_a_subagent`.
- Council quota: one atomic `consume(amount=3)` up front; children carry
  no-op ledgers; refusal spawns nothing (tested).

## 2. Findings and risk ranking

| # | Severity | Finding |
|---|---|---|
| F-1 | **High** | **Stream termination can hang.** `_close_subscribers` uses `put_nowait(None)` with `QueueFull` suppressed. A slow subscriber whose 256-slot queue is full **never receives the close sentinel**; `follow_logs` then blocks forever on `queue.get()` — an unbounded wait held open in `_run_streaming`. |
| F-2 | **High** | **Replay gap (lost entries).** `follow_logs` snapshots `list(agent.log)`, yields (awaiting between yields), *then* subscribes. Entries logged between the snapshot and `subscribers.append` are neither replayed nor streamed — silent, timing-dependent loss for late subscribers. No sequence numbers exist to dedup/resume. |
| F-3 | **High** | **Unbounded prompt/context/system/name/tools.** `_spec_from_params` accepts arbitrarily large strings (multi-MB prompts are stored, echoed back on every `subagent.list`, and re-serialised per poll). Council topics inherit the same hole. `tools` array length is unbounded. |
| F-4 | **High** | **Unbounded retention & log growth.** Terminal agents are never evicted from `_runtimes`/`_order`/`_pipelines`/`_pipeline_tasks`; each `agent.log` list grows without cap and `subagent.get` serialises all of it. A long-lived sidecar grows monotonically. |
| F-5 | **Medium** | **No upper bounds on limits or stages.** `max_turns=10**9`, `max_tokens=10**12`, `max_duration=10**9` are accepted (a watchdog then ticks for years); `subagent.pipeline` accepts any number of stages (registry spam past the concurrency gate, since stages bypass the `spawn` cap). |
| F-6 | **Medium** | **`grace_seconds` unvalidated.** `subagent.cancel` does `float(grace)` uncaught — `"abc"` → `ValueError` → INTERNAL instead of `invalid_params`; a huge value makes cancel wait unboundedly. |
| F-7 | **Medium** | **Failure text is not redacted at source.** `_finish(error=f"{type(exc).__name__}: {exc}")` stores raw provider exception text into the record returned by `subagent.get`/`list` (a *result* payload — the bridge's error-path redaction never sees it). Provider exceptions can embed URLs with keys. |
| F-8 | **Medium** | **Frontend retained log is unbounded.** The route accumulates `[...prev.log, entry]` forever; rendering is virtualised but state/memory is not capped, and there is no truncation indicator. |
| F-9 | **Low** | **No explicit stream state.** A dropped `subagent.logs` stream silently leaves the last snapshot; the acceptance list requires explicit live/ended/disconnected states. |
| F-10 | **Low** | **Echo/sidecar parity gaps.** Echo enforces no concurrency cap, no prompt/stage/limit bounds; `num()` silently swallows bad `max_*` instead of failing like `_positive_int`. |
| F-11 | **Low** | Spawn-dialog numeric inputs accept values the sidecar (post-fix) will refuse; no client-side clamp/hint. `councils` state array grows unbounded. Pause/Resume button swap can drop keyboard focus at the transition. |

Non-findings (verified sound, no change proposed): tool-grant fail-closed
walls, registry snapshot/restore, ledger detachment, cancel idempotency,
pause/resume state machine, duration watchdog, selection fallback logic,
virtualised log DOM bound, axe/RTL/offline coverage, provenance format.

## 3. Proposed scope (exact files)

**Backend — `dream/subagents.py`**
- Bounded per-agent log ring: `MAX_LOG_ENTRIES = 500` (oldest dropped, a
  `log_dropped` counter surfaces truncation), per-message cap
  `MAX_LOG_MESSAGE_CHARS = 2_000`; monotonic `seq` on `LogEntry` (additive
  wire field).
- Deterministic replay: subscribe **before** snapshot, replay history, then
  drain the queue deduplicating by `seq` — no gaps, no duplicates; guaranteed
  close: on `QueueFull`, evict the oldest item so the `None` sentinel always
  lands.
- Spec bounds (fail closed in `SubAgentSpec.__post_init__`): prompt ≤ 16 000
  chars, context ≤ 32 000, system_prompt ≤ 8 000, name ≤ 120, tools ≤ 32
  entries / 100 chars each; upper caps `max_turns ≤ 100`,
  `max_tokens ≤ 200 000`, `max_duration ≤ 3 600`.
- `MAX_PIPELINE_STAGES = 16`; bounded retention `MAX_RETAINED = 200`
  (evict oldest **terminal** agents only, with their pipeline bookkeeping;
  active agents are never evicted); completed pipeline driver tasks reaped.
- Redact stored failure text with `dream.security.secrets.redact_text`.

**Bridge — `dream/bridge/methods.py` (subagent section only)**
- Validate `grace_seconds` (number, 0–30) → `invalid_params` otherwise;
  surface the new `ValueError`s from spec/stage caps as `invalid_params`
  (already the pattern); no method added or removed; wire shapes unchanged
  except additive `seq`/`log_dropped` fields.

**Docs — `docs/architecture/subagents.md`**: record the new bounds and
replay semantics (design of record for this module).

**Echo parity — `apps/desktop/src/lib/bridge/echo-subagents.ts`**
- Mirror every new bound (prompt/context/system/name/tools caps, stage cap,
  limit caps with invalid-params on malformed values, concurrency cap 8,
  log ring + `seq`) so echo and sidecar fail identically.

**Frontend**
- `routes/subagents.tsx`: cap retained streamed log at 1 000 entries with a
  localized truncation line; explicit stream status (replaying → live →
  ended / disconnected) rendered near the log; cap the `councils` array;
  preserve focus when Pause⇄Resume swap.
- `components/subagents/subagent-detail.tsx`: stream-status line +
  truncation notice pass-through (rendering only).
- `components/subagents/spawn-dialog.tsx`: clamp numeric limits to the
  sidecar bounds (min/max attributes + clamp on change).
- `apps/desktop/scripts/generate-locales.mjs` + regenerated
  `src/locales/*/subagents.json`: new keys (stream states, truncation
  notice), fully translated for `fa` (gate) and en; other locales fall back
  per existing policy.
- `apps/desktop/src/lib/bridge/types.ts`: additive optional `seq` on
  `BridgeLogEntry`, `log_dropped` on `BridgeSubagent`.

**Tests (deterministic; no sleeps beyond existing bounded polling helpers,
no network, no credentials)**
- `tests/test_subagents.py` (extend): log ring bound + drop counter; seq
  monotonicity; replay-then-live no-gap/no-dup under a synchronised
  concurrent logger (asyncio.Event handshakes); full-queue close still
  terminates; retention eviction never touches active agents; pipeline
  stage cap; spec bounds; error redaction; shutdown leaves no pending tasks.
- `tests/test_bridge_subagent_schedule.py` (extend): oversized prompt /
  excessive stages / bad `grace_seconds` / over-cap limits fail closed with
  `invalid_params`; logs stream replay determinism at the RPC layer;
  cancel/pause/resume race (event-gated backend) idempotency.
- `apps/desktop/src/lib/bridge/echo-subagents.test.ts` (extend): contract
  parity for every new bound.
- `apps/desktop/src/routes/subagents.test.tsx` (extend): stream status
  states, bounded retained log + truncation line, terminal-fallback focus,
  offline/error/empty already covered — kept green.
- Existing P-12/P-13/P-14 suites untouched and re-run as regression.

## 4. Explicitly out of scope

- No provenance schema change; no new provenance writes (adding
  `subagent_spawn` records is possible but is a **separate** decision — the
  vocabulary exists yet no call site writes it; not needed for 3.2).
- No workflow/release/tag changes (`v0.4.7` not created), no provider
  routing, Web Gateway, scheduler, or reminder edits.
- No second subagent engine; no process/network isolation change; no
  approval-policy change (fail-closed walls already verified).
- `pyproject.toml` version stays `0.4.6` unless separately instructed.

## 5. Test matrix (acceptance ↔ tests)

| Acceptance item | Covered by |
|---|---|
| 1 param/bound validation | new spec/bridge bound tests (py + echo) |
| 2 spawn/pipeline/council scope isolation | existing store/registry/ledger tests (regression) + stage-cap test |
| 3 replay ordering, no duplication | new seq/replay tests (py + route test) |
| 4 disconnect/reconnect/terminal completion | full-queue close test, route stream-status tests, existing stage-d offline |
| 5 cancel/pause/resume races | event-gated race tests (no sleeps) |
| 6 shutdown cleanup | no-leaked-tasks test + existing cancel_all tests |
| 7 echo/sidecar parity | echo-subagents parity tests |
| 8 project/session/provenance non-leakage | existing P-14/P-10 suites re-run; parent_session_id inert-string assertion |
| 9 frontend loading/offline/error/empty/terminal | existing subagents.test.tsx + new stream states |
| 10 a11y/RTL/keyboard/bounded rendering | stage-d-accessibility + log-tail bound test + focus test |
| 11 privacy-safe errors/logs | redaction test (py) |
| 12 P-12/P-13/P-14 preservation | full pytest + vitest matrix |
