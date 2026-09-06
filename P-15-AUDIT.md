# P-15 Audit Report — Subagent Monitor & Execution Observability

> Checklist item **3.2 Subagent monitor** — completion and hardening pass.
> Scope approved against `P-15-SYNTHESIS.md` §3 (full scope, F-1…F-11;
> provenance untouched per explicit decision).

- Base: `fb45ad8da8270c023acf8e24c293ace1a10cf066` (`origin/main`, P-14 merge,
  PR #128 merged, post-merge CI green on that exact SHA).
- No `v0.4.7` tag created; `pyproject.toml` stays `0.4.6`.
- Provenance record format, workflows, release automation, provider routing,
  Web Gateway, scheduler and reminder behaviour: **untouched**.

## 1. What changed and why (finding → change)

| Finding | Change |
|---|---|
| F-1 stream can hang on a full subscriber queue | `SubAgentManager._offer`: a full queue drops its **oldest** item, so the `None` close sentinel always lands; slow clients can no longer hold `subagent.logs` open past terminal. |
| F-2 replay gap (lost entries) | `LogEntry.seq` (per-agent monotonic); `follow_logs` subscribes **before** snapshotting, replays, then drains the queue skipping already-replayed seqs — no gaps, no duplicates. |
| F-3 unbounded prompt/context/system/name/tools | `SubAgentSpec.__post_init__` bounds: prompt ≤ 16 000 (refused), context ≤ 32 000 (truncated — pipeline hand-me-down), system ≤ 8 000 (refused), name ≤ 120 (truncated), tools ≤ 32 × 100 chars (refused). Council topic refused > 16 000 **before** any quota turn is consumed. |
| F-4 unbounded retention & log growth | Per-agent log ring (`MAX_LOG_ENTRIES = 500`, drops counted in `log_dropped`; messages ≤ 2 000 chars); `MAX_RETAINED_SUBAGENTS = 200` evicting only **terminal** agents; completed pipeline driver tasks reaped. |
| F-5 no upper limit caps / stage cap | `max_turns ≤ 100`, `max_tokens ≤ 200 000`, `max_duration ≤ 3 600 s`; `MAX_PIPELINE_STAGES = 16` enforced in the manager **and** pre-validated in the bridge before any stage spawns. |
| F-6 `grace_seconds` unvalidated | Bridge validates it as a number in `[0, 30]` → `invalid_params` otherwise (`MAX_CANCEL_GRACE_SECONDS`). |
| F-7 raw failure text on the result path | `_safe_error`: failure strings pass `redact_text` and the message bound at source, since `subagent.get/list` return them as results the error-path redaction never sees. |
| F-8 unbounded frontend log state | Route retains ≤ 1 000 streamed lines; overflow is dropped from the head and counted; the detail pane says "N earlier lines dropped…" (localized). |
| F-9 no explicit stream state | Explicit phases connecting → live → ended / disconnected, rendered as a `role="status"` line beside the activity log. |
| F-10 echo/sidecar parity gaps | `echo-subagents.ts` mirrors every bound (`SUBAGENT_BOUNDS`), fails malformed `max_*` with `invalid_params` like `_positive_*`, enforces the concurrency cap (RESOURCE_EXHAUSTED) on direct spawns, carries `seq`/`log_dropped`, ring-buffers logs, evicts terminal agents. |
| F-11 form/values/focus | Spawn dialog clamps numeric limits to the caps (min/max + clamp, "up to N" hints), Add-stage disabled at 16; councils array capped at 50; Pause⇄Resume swap restores keyboard focus onto the replacement control. |

Additive wire fields only: `LogEntry.seq`, `SubAgent.log_dropped`
(optional in `types.ts`; every existing consumer is unaffected).

## 2. Verification matrix (all executed on this checkout)

| Check | Result |
|---|---|
| `python -m pytest -q` (full) | **3545 passed, 16 skipped** (was 3505 — +40 new deterministic tests) |
| `python -m ruff check .` | All checks passed |
| `python tools/check_suite_count.py` | 3550 collected ≥ 652 — pass |
| `tools/check_locales.py` | PASS — 8 locales × 30 namespaces, identical trees, fa gate PASS |
| `npm run typecheck` | clean |
| `npm run lint` | 0 errors (13 pre-existing warnings, untouched files) |
| `npm run format:check` | clean |
| `npm run test` | **784 passed (111 files)** (was 761 — +23 new tests) |
| `npm run build` | clean |
| `npm run performance:check` | pass (`"pass": true`) |
| `npm run accessibility:check` | 13 passed (3 files), includes the subagent dashboard axe run |

### New deterministic tests (no sleeps beyond the suite's existing bounded
polling helpers, no network, no credentials)

- `tests/test_subagents.py` (+18): spec bounds (each cap, at-cap acceptance),
  stage cap, log ring + drop counter + message truncation, seq monotonicity,
  **no-gap/no-dup replay handover under a concurrent logger (Event-gated)**,
  **full-queue close-sentinel termination**, terminal-only retention eviction
  (paused keeper survives), pipeline-driver reaping, redacted+bounded failure
  text, carried-context truncation, shutdown leaves no `subagent:`/`pipeline:`
  tasks pending.
- `tests/test_bridge_subagent_schedule.py` (+15): oversized prompt/system/
  tools, over-cap limits, stage cap fails before any spawn (list stays empty),
  malformed/out-of-range `grace_seconds`, RPC-level cancel idempotency, two
  late subscribers replay identical ordered seqs, terminal-stream termination,
  pause/resume/cancel race with explicit post-terminal refusals, `log_dropped`
  on the wire, council topic bound, `parent_session_id` inert-string proof
  (session/project non-leakage at the join).
- `apps/desktop/src/lib/bridge/echo-subagents.test.ts` (+12): contract parity
  for every bound, RESOURCE_EXHAUSTED at 8 concurrent, seq/log_dropped shape,
  identical replay for two subscribers, malformed `max_*` fail-closed.
- `apps/desktop/src/routes/subagents.test.tsx` (+4): explicit stream states
  (ended, disconnected keeps last snapshot), deterministic newest-first
  selection fallback, Pause⇄Resume keyboard-focus preservation.
- `apps/desktop/src/components/subagents/subagent-detail.test.tsx` (new, 5):
  stream-phase status role, truncation notice presence/absence, stable
  accessible control names across running/paused/terminal, terminal error
  alert rendering.

### Regression preservation

- P-12/P-13/P-14 suites all run inside the full matrix above — unchanged and
  green (`test_bridge_projects.py`, scheduler/reminder suites, workspace
  suites, stage-D accessibility/offline, echo-projects, etc.).
- SEC-08…SEC-11 behaviour untouched: no tool-approval, sandbox, network or
  provider path was modified; `build_child_tools` fail-closed walls and the
  council quota path are byte-identical apart from the pre-quota topic bound.

## 3. Honest notes / environment-bound results

- Rust desktop shell checks (`cargo fmt/clippy/build/test`) were **not run
  locally** (no Rust toolchain in this sandbox); no Rust file changed. CI runs
  them on the PR.
- The multi-Python matrix (3.10–3.13) runs in CI; locally verified on the
  sandbox's Python 3.11 only.
- Regenerating locales revealed the generator is **stale for
  `memory.reminders`** (P-13 keys live only in the committed JSON). Those
  files were deliberately restored; only `subagents.json` files changed. The
  generator gap is a pre-existing issue, out of P-15 scope — flagged here for
  a future phase.
- `test_retention_evicts_only_terminal_agents` shrinks the retention cap via
  `monkeypatch.setattr` to keep the test fast; production value stays 200.
- The disconnected-stream UI state is reachable in sidecar mode via transport
  loss; the test drives it with an injected failing transport (the same
  pattern the existing offline suites use).

## 4. Files changed (each justified in §1)

Backend: `dream/subagents.py`, `dream/bridge/methods.py`, `dream/council.py`.
Frontend: `apps/desktop/src/lib/bridge/{echo-subagents.ts,types.ts}`,
`apps/desktop/src/routes/subagents.tsx`,
`apps/desktop/src/components/subagents/{subagent-detail.tsx,spawn-dialog.tsx}`.
Locales: `apps/desktop/scripts/generate-locales.mjs`,
`apps/desktop/src/locales/*/subagents.json`, `TODO-i18n.md` (6 new keys,
en+fa translated, others fall back per policy).
Docs: `docs/architecture/subagents.md` (§2.7), `P-15-SYNTHESIS.md`, this file.
Tests: `tests/test_subagents.py`, `tests/test_bridge_subagent_schedule.py`,
`apps/desktop/src/lib/bridge/echo-subagents.test.ts`,
`apps/desktop/src/routes/subagents.test.tsx`,
`apps/desktop/src/components/subagents/subagent-detail.test.tsx` (new).
