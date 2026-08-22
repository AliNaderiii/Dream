# UI Stage D — operational workspaces handoff

Date: 2026-08-22  
Branch: `arena/01a02863-dream` (Arena-fixed; no alternate branch was created)  
Base accepted for this stage: Gate A–C head `41c6045eebb1c7182bbf3c731f0beb7fea16c738`  
Review PR: #74

## Scope and specialist decomposition

The orchestrator reviewed the complete Stage D diff after seven implementation/debugging roles reached their checks:

1. **Bridge lifecycle specialist** — bounded call/stream waits, AbortSignal settlement, late-chunk suppression, and shared offline/reconnect state.
2. **Session specialist** — bridge-backed create/list/rename/delete, safe reconciliation, keyboard actions, empty/loading/error/offline states, and a virtualized 1,000-session list.
3. **Memory specialist** — explorer lifecycle states, shared filters, score explainability, RTL labels, cancellation, and bounded cards/timeline rendering.
4. **Skills specialist** — optimistic enable rollback, import validation, delete/export behavior, lifecycle states, virtualization, and pure model extraction.
5. **Subagent specialist** — live lifecycle/status badges, limits, pause/resume/cancel wiring, bounded tail following, and proposer/critic/judge council results.
6. **Scheduler and locale specialist** — bilingual natural-language schedule round trips, cron and three-date previews, bounded history, approvals, and generated locale parity.
7. **Regression/review specialist** — test-strength audit, protected-path audit, TypeScript, ESLint, Prettier, locale/token checks, Vite/Ladle builds, full Vitest, and Python baseline.

No role changed `dream/`, Python `tests/`, the framed JSON-RPC protocol, kernel behavior, metering, or ledger logic.

## Shared bridge contract

`BridgeClient.call` and `BridgeClient.stream` accept timeout and AbortSignal options. Calls default to 30,000ms and streams to 300,000ms; callers can use narrower bounds. Settlement clears timeout and abort listeners. An aborted/timed-out stream rejects the renderer await and suppresses both per-call and global late chunk delivery.

Tauri invocation itself is not natively cancellable. This implementation bounds renderer waits and prevents stale renderer updates; it does **not** claim to stop already-dispatched sidecar work.

The shared `BridgeOfflineBanner` observes bridge state and provides a localized reconnect action. `stage-d-offline.test.tsx` renders the integration in all five Stage D surfaces.

## Per-surface evidence

| Surface | Empty | Loading skeleton | Actionable error | Bridge-dead | Cancellation / spinner settlement | Virtualization |
| --- | --- | --- | --- | --- | --- | --- |
| Sessions | `renders the empty session state` | 5 rows | failed list → Retry → empty | Stage D sessions offline integration | pending list aborted on unmount; loading status absent afterward | 1,000 → 26 mounted |
| Memory | `renders the real empty state` | 5 rows | failed list → Retry → seeded result | Stage D memory offline integration | superseded search aborts first load; loading status absent | 1,000 → 8 mounted |
| Skills | `renders the installed-skills empty state` | 5 cards | failed registry → Retry → installed rows | Stage D skills offline integration | pending list aborted on unmount; loading status absent afterward | 1,000 → 10 mounted |
| Subagents | `starts empty and offers a way in` | 5 roster rows + 1 detail panel | failed roster → Retry → empty | Stage D subagents offline integration | pending roster/tool work aborted on unmount; loading status absent afterward | 1,000 log rows → 5 mounted |
| Scheduler | `shows the empty state before any schedule exists` | 3 cards | failed list → Retry → empty | Stage D scheduler offline integration | superseded natural-language preview aborts; ellipsis spinner absent | 1,000 history rows → 26 mounted |

Focused executable evidence:

```text
$ npm run test -- --run src/lib/bridge/bridge.test.ts src/components/layout/sidebar.test.tsx src/routes/stage-d-offline.test.tsx src/routes/memory.test.tsx src/components/memory/memory-model.test.ts src/components/memory/memory-score.test.tsx src/routes/skills.test.tsx src/components/skills/skills-model.test.ts src/routes/subagents.test.tsx src/components/subagents/subagent-log-tail.test.tsx src/routes/scheduler.test.tsx src/components/scheduler/schedule-history.test.tsx
session_fixture_rows=1000 mounted_rows=26
memory_fixture_rows=1000 mounted_rows=8
skills_fixture_rows=1000 mounted_rows=10
subagent_log_rows=1000 mounted_rows=5
scheduler_history_rows=1000 mounted_rows=26
Test Files  12 passed (12)
Tests       82 passed (82)
```

`VirtualList` uses logical layout, bounded overscan, estimated row sizes, keyboard-reachable row content, and tail-following only when requested. Every measured fixture remains under the `<60` acceptance bound.

## Session manager

The sidebar consumes protocol v3.16 session methods without changing their payloads. Tauri-backed startup reconciles bridge rows into normalized store rows; browser echo mode keeps the local demonstration store authoritative. Create awaits the bounded bridge result, merges it into the store, selects it, and navigates to `/chat/:sessionId`. Rename and delete expose keyboard-accessible action menus and confirmation.

The navigation regression retained the exact `Conversation` heading assertion but now waits for the bridge-backed asynchronous navigation to settle:

- **Before:** synchronous `getByRole('heading', { name: 'Conversation' })` immediately after click.
- **After:** awaited `findByRole('heading', { name: 'Conversation' })`.
- **Reasoning:** the content assertion is identical; only its timing reflects the now-bounded asynchronous create RPC. This is not a weaker assertion.

## Memory explorer and score explainability

`MemoryScore` mirrors the protocol scoring model rather than inventing a UI-only ranking:

```text
weighted total =
  0.55 × relevance +
  0.20 × recency +
  0.15 × importance +
  0.10 × usage
```

Four accessible meters expose factor values and weights, followed by the weighted total. Relevance is explicitly unavailable for rows that were not retrieval-ranked. Persian coverage verifies real localized factor labels in an RTL document; numeric data remains normalized and direction-safe.

After the route reached the regression-edit threshold, query normalization was extracted to pure `components/memory/memory-model.ts`. Its unit tests pin empty-filter normalization, settled search text, date bounds, kind/sort values, and ten-star-to-protocol importance mapping. The route now delegates query construction to this model.

## Skills manager extraction

After `skills.tsx` crossed ORD-2, feature edits stopped until unstable behavior moved into pure `components/skills/skills-model.ts`. Four unit tests pin:

- deterministic enabled/name sorting;
- optimistic enable state and exact rollback;
- post-save selection;
- locale-neutral validation issue descriptors.

The route delegates those transitions to the model. Focused route/model tests verify enabled state, optimistic toggling, selection, valid/invalid import, conflict choices, delete confirmation, lifecycle states, cancellation, and 1,000-row bounding.

## Subagents and council

The roster and detail surfaces expose normalized live status badges plus turn, token, duration, elapsed, and progress/limit information. Detail controls are wired directly to bounded `subagent.pause`, `subagent.resume`, and `subagent.cancel` RPCs. The log tail uses `VirtualList`, keeps tail ownership while sticky, and measured 5 mounted entries for 1,000 log rows.

The council path creates proposer, critic, and judge columns. Route coverage asserts all three role regions and waits for the winner strip. It uses protocol responses and does not synthesize a UI-only winner.

## Scheduler, bilingual preview, and fail-closed approval

The scheduler round-trips English and Persian natural-language rhythm text through the existing `nl_schedule` bridge behavior, displays the resulting cron expression, and computes exactly three preview rows. Each row displays one document-locale Gregorian timestamp and one RTL Jalali timestamp. The strengthened test asserts exactly three list rows and exactly three Jalali cells; every Jalali cell must contain Persian digits.

Assertion-strength note:

- **Before:** one singular Jalali element merely matched Persian digits.
- **After:** exactly three preview list rows and exactly three Jalali cells, with every Jalali cell matching Persian digits.
- **Reasoning:** the replacement is strictly stronger and matches the three-date requirement.

History is separately virtualized (1,000 → 26 mounted). Approval-required runs display a reason identifying the blocked risk gate. The tested no-approval path ends as `approval denied`; it never executes first and asks later.

## Localization and RTL

All new user-facing strings are generated locale leaves across eight locales. The English-only Stage D backlog for non-Persian locales remains explicit in `src/locales/TODO-i18n.md`. Persian translations for Stage A–D keys have no English fallback.

```text
$ npm run locales:check
Locale integrity: PASS — 8 locales × 14 namespaces; 655 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=267, ja=267, es=267, de=267, fr=267, ko=267; fa gate=PASS
```

Components use logical properties (`start/end`, `ms/me`, `ps/pe`, `border-e`) and isolate cron/code or mixed-direction content where needed. Persian score labels and Jalali dates have executable RTL coverage.

## RF-4 — `bridge.test.ts` assertion audit

No pre-existing assertion in `src/lib/bridge/bridge.test.ts` was modified, removed, skipped, or weakened. Four test cases and their transport fixtures were added:

| Added case | Before | After | Reasoning |
| --- | --- | --- | --- |
| Bounded call timeout | No assertion | A hanging call with `timeoutMs: 5` must reject with `slow.method timed out after 5ms` | Pins timeout settlement and method-specific diagnostics. |
| AbortSignal call cancellation | No assertion | A hanging call must reject with `cancel.method was cancelled` after abort | Pins caller cancellation instead of indefinite UI waits. |
| Independent stream timeout | No assertion | A hanging stream with `timeoutMs: 5` must reject with `slow.stream timed out after 5ms` | Ensures long-stream bounds are independently configurable. |
| Cancelled-stream late chunk suppression | No assertion | Aborted stream rejects as cancelled; a subsequently emitted chunk leaves both callback and global event arrays exactly empty | Prevents stale stream writes after settlement. |

Timeout/cancellation coverage only became stricter.

## Other Stage D test additions

The modified route/component suites add assertions where no equivalent assertion existed before: lifecycle states, retries and call counts, cancellation spinner clearing, five surface integrations of the offline state, Persian score labels, exact weighted factors, and concrete 1,000-row mount counts. Existing functional assertions remain. The only changed existing assertions are the non-weakened session timing adaptation and the strictly stronger scheduler three-date assertion documented above.

## Gate D command evidence

### Desktop tests

```text
$ npm run test
Test Files  62 passed (62)
Tests       484 passed (484)
command_palette_open_ms=54.521 budget_ms=100
```

### TypeScript, lint, formatting, tokens, and locales

```text
$ npm run typecheck
> tsc --noEmit
# exit 0

$ npm run lint
✖ 14 problems (0 errors, 14 warnings)

$ npm run format:check
All matched files use Prettier code style!

$ npm run tokens:check
Tokens Studio schema-compatible import: PASS — 12 sets, 208 tokens, 12 themes.
Contrast gate: PASS — 108 AA checks.

$ npm run locales:check
Locale integrity: PASS — 8 locales × 14 namespaces; 655 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=267, ja=267, es=267, de=267, fr=267, ko=267; fa gate=PASS
```

ESLint warnings are known compiler/fast-refresh advisories; there are zero lint errors.

### Builds

```text
$ npm run build
✓ 2039 modules transformed.
✓ built in 5.25s
```

The visible main-chunk advisory remains (`index-CcqqgM0P.js` 1,006.32kB, 313.01kB gzip). It was not hidden and the threshold was not raised. Route splitting/lazy panes remain the explicit Stage E resolution.

```text
$ npm run storybook:build
✓ 1998 modules transformed.
✓ built in 13.21s
✓ Meta.json successfully created.
Ladle finished the production build in 14s producing 1.53 MiB of assets.
```

### Python regression baseline

A first run had a timing-only Telegram polling failure while Vite and Ladle builds ran concurrently (`offsets` was `[0]` before the next 10ms poll). The unchanged test passed immediately in isolation, then the full suite passed without concurrency:

```text
$ .venv/bin/pytest -q tests/test_connectivity_adapters.py::test_telegram_adapter_polls_and_delivers_normalised_messages
1 passed in 0.12s

$ .venv/bin/pytest -q
1748 passed, 11 skipped in 59.86s
```

### Protected paths and patch integrity

```text
$ git diff --stat -- dream/ tests/
# no output
protected_paths=dream/,tests/ unchanged

$ git diff --check
diff_check=PASS
```

## Gate decision

Gate D can be marked green only against the final full-suite rerun and static checks appended to `UI-GATES.md`. Stage E owns route splitting/lazy panes, performance budgets, the light-muted ≥5.0:1 target, all-five-surface axe/reduced-motion verification, and preservation of the visible >500kB advisory until it is solved.
