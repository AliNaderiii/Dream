# UI Stage E — performance, accessibility, and regression handoff

- Date: 2026-08-22
- Branch: `arena/01a02863-dream` (Arena-fixed; no alternate branch was created)
- Stage D base: `730435a`
- Review PR: #74

## Scope and specialist decomposition

Seven specialist roles remained active until their focused gates passed; the orchestrator then reviewed the combined diff:

1. **Bundle architecture specialist** — route-level `React.lazy`, nested pane loading, on-demand locale chunks, skeleton Suspense boundaries, and stable vendor partitioning.
2. **Transcript performance specialist** — variable-height message virtualization at 100+ rows, bounded overscan, measured rows, sticky initial/tail rendering, streaming integration, and a pure pane feed model.
3. **Runtime budget specialist** — executable palette, route, streaming-task, heap-growth, bundle, cold-start, rejection, and event-loop-yield guards with JSON output.
4. **Accessibility specialist** — all-five-surface axe coverage, required meter semantics, reduced-motion coverage, and assistive-technology limitation review.
5. **Token and contrast specialist** — canonical JSON/CSS round trip, Light muted adjustment, and a dedicated ≥5.0 validator floor across four accents.
6. **CI and localization specialist** — performance artifact wiring, exact eight-locale loader behavior, `fa=0`, and isolated Python timing guidance.
7. **Regression and handoff specialist** — assertion-strength audit, TypeScript/ESLint/Prettier/build/Ladle/Python gates, protected-path verification, and final diff review.

No role changed `dream/`, Python `tests/`, the framed JSON-RPC protocol, kernel behavior, metering, or ledger logic.

## Bundle resolution

The warning threshold remains Vite’s existing 500kB setting. The advisory was removed by changing the module graph, not by hiding output or raising a budget.

Before Stage E:

```text
index-CcqqgM0P.js  1,006.32 kB │ gzip: 313.01 kB
(!) Some chunks are larger than 500 kB after minification.
```

After route, nested-pane, locale, and vendor splitting:

```text
✓ 2044 modules transformed.
dist/assets/index-BScXyVnd.js          203.78 kB │ gzip: 63.22 kB
dist/assets/react-vendor-BSOuYUyy.js   255.94 kB │ gzip: 83.25 kB
dist/assets/ui-vendor-Cb0Ln_mG.js       76.66 kB │ gzip: 24.94 kB
dist/assets/i18n-vendor-CkSKoGz1.js     49.67 kB │ gzip: 16.37 kB
dist/assets/pane-workspace-Cf2TMdji.js  28.77 kB │ gzip:  9.72 kB
✓ built in 5.00s
```

Every emitted JavaScript chunk is below 500kB uncompressed. The main entry is 63.22kB gzip, below the 250kB gzip requirement. Dashboard, chat, memory, skills, projects, providers, settings, data, data-set detail, provenance, scheduler, subagents, and connectivity routes are lazy. The chat route adds a separate pane-workspace boundary. Route fallbacks expose three structural skeleton shapes and obey reduced motion.

The locale backend uses lazy `import.meta.glob` imports. Startup installs English plus the active locale; subsequent languages load on demand, while tests deliberately await all supported resources before singleton initialization.

## RF-1 TypeScript configuration audit

Stage E changes exactly two existing `tsconfig.json` properties. Both increase the code checked by TypeScript; no strictness flag, module rule, path alias, or exclusion was loosened.

| Property                | Before                                                             | After                                                                                 | Justification                                                                                                                                                                                                                                                                             |
| ----------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `compilerOptions.types` | `["vite/client", "@testing-library/jest-dom"]`                     | `["vite/client", "@testing-library/jest-dom", "node"]`                                | The checked performance harness and source-policy tests import Node built-ins such as `node:fs`, `node:path`, `node:perf_hooks`, and `node:child_process`. Adding the Node declarations makes those APIs type-safe; it does not broaden runtime globals or relax any compiler diagnostic. |
| `include`               | `["src", ".ladle/**/*.tsx", "vite.config.ts", "eslint.config.js"]` | `["src", "scripts/**/*.ts", ".ladle/**/*.tsx", "vite.config.ts", "eslint.config.js"]` | Includes `scripts/perf-check.ts` in the required `tsc --noEmit` gate. This is a stricter scope increase: the executable CI harness can no longer drift outside TypeScript validation.                                                                                                     |

Literal changes:

```diff
-    "types": ["vite/client", "@testing-library/jest-dom"],
+    "types": ["vite/client", "@testing-library/jest-dom", "node"],
...
-  "include": ["src", ".ladle/**/*.tsx", "vite.config.ts", "eslint.config.js"],
+  "include": ["src", "scripts/**/*.ts", ".ladle/**/*.tsx", "vite.config.ts", "eslint.config.js"],
```

`strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `noUncheckedSideEffectImports`, `noImplicitOverride`, and `verbatimModuleSyntax` remain unchanged.

## Transcript virtualization

`VariableVirtualList` is dependency-free and uses logical block/inline positioning, measured row heights with an estimate fallback, binary offset lookup, bounded overscan, viewport resize observation, and sticky tail behavior. Its offset/range/tail calculations were extracted to pure `variable-virtual-geometry.ts` after regression churn; unit tests pin mixed measured/estimated offsets, bounded ranges, and release of tail ownership when the reader scrolls away. `VirtualMessageList` retains tool cards, user/assistant alignment, live/busy streaming semantics, error and empty-state continuity, and transcript labelling.

The pane threshold rule was honored by extracting the unstable feed projection into pure `components/panes/pane-chat-model.ts`, with tests for settled identity, deterministic provisional-row creation, ordering, and non-mutation. The pane delegates rendering to the independently tested virtual component; no further feature logic was added in-component.

```text
chat_fixture_rows=120 mounted_message_rows=11
message_fixture_rows=500 mounted_message_rows=11
variable_fixture_rows=1000 mounted_rows=15
```

The newest settled row is present on initial mount, and an active streaming row remains in the same bounded feed. Existing frame batching keeps a 500-chunk stream to one write per animation frame.

## R4-1 assertion-strength audit

### `src/routes/chat.test.tsx`

No pre-existing assertion was removed, changed, skipped, or weakened.

| Existing case            | Before                                      | After                                                                          | Reasoning                                                                                                                                                                            |
| ------------------------ | ------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Route smoke              | `expect(container).toBeTruthy()`            | Identical                                                                      | Preserved exactly. Lazy pane loading does not require weakening the route container contract.                                                                                        |
| Bridge-state smoke       | `expect(container.innerHTML).toBeDefined()` | Identical                                                                      | Preserved exactly.                                                                                                                                                                   |
| Per-test setup           | No transcript reset                         | `mockPaneChatStore.transcripts = {}` before each case                          | Isolation only; not an assertion change. Prevents the new 120-row fixture leaking into existing cases.                                                                               |
| 100+ transcript behavior | No assertion                                | Await newest row `Transcript message 119`; mounted rows must be `>0` and `<60` | New strictly additive behavior coverage for asynchronous lazy loading and real pane virtualization. The async query asserts the final user-visible row, not merely chunk resolution. |

Virtualization did **not** make either old synchronous assertion impossible, so both remain synchronous and unchanged. The new behavior assertion is async because `PaneWorkspace` is intentionally lazy; it waits for equivalent-or-stronger visible content.

### `src/components/chat/virtual-message-list.test.tsx`

This file did not exist at the Stage D base, so there are no committed existing assertions to weaken. One draft assertion changed during Stage E and is recorded for review:

| Draft before                                                              | Final after                                                                                        | Reasoning                                                                                                                                                                    |
| ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Expected `Message 499` to be absent on the first render of a 500-row feed | Expects `Message 499` to be present while still requiring `0 < mounted rows < 60`                  | The draft contradicted chat’s sticky-tail contract. The final assertion is stronger and user-relevant: initial mount shows the newest message **and** keeps the DOM bounded. |
| Streaming test dispatched a raw DOM scroll event                          | Uses Testing Library `fireEvent.scroll`; visible streaming text and `<60` assertions are unchanged | Removes an `act(...)` warning without changing behavior or assertion strength.                                                                                               |

### Other changed test assertions

| File                                          | Before                                              | After                                                                             | Reasoning                                                                                                         |
| --------------------------------------------- | --------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `app-shell.test.tsx` dashboard heading        | Synchronous `getByRole` for `Dashboard`             | Awaited `findByRole` for the same `Dashboard` heading, plus cold-render `<2000ms` | Route is now lazy. Name/role semantics are identical; only settlement timing changed, and the budget is additive. |
| `app-shell.test.tsx` memory/skills regions    | Synchronous `getByRole('region', { name: label })`  | Awaited `findByRole` with the identical role/name for both routes                 | Equivalent async replacement required by lazy route chunks; no content weakening.                                 |
| `app-shell.test.tsx` unknown-route redirect   | Synchronous `getByRole` for `Dashboard`             | Awaited `findByRole` for the same heading                                         | Redirect now crosses a lazy boundary; target assertion is unchanged.                                              |
| `app-shell.test.tsx` known chat session       | Synchronous heading level 2 named `Persian grammar` | Awaited heading level 2 with the identical name                                   | Nested pane chunk is lazy; exact accessible contract remains.                                                     |
| `app-shell.test.tsx` route timing             | No route timing assertion                           | Settings navigation must render Appearance in `<300ms`                            | New warm-route guard.                                                                                             |
| `memory-score.test.tsx` unavailable relevance | Required `aria-valuetext="Unavailable"`             | Also requires `aria-valuenow="0"`                                                 | Strictly stronger and fixes axe’s required-ARIA finding.                                                          |

No test was skipped. No timeout/cancellation assertion changed.

## Performance JSON and CI artifact

`apps/desktop/scripts/perf-check.ts` launches the representative runtime tests, extracts their explicit measurements, validates the production bundle, measures retained heap with `--expose-gc`, writes `performance-results.json`, and emits the same report as JSON. The generated report is ignored locally and uploaded by Desktop CI as `desktop-performance-${{ github.sha }}`.

```json
{
  "paletteOpenMs": 52.125,
  "routeChangeMs": 168.487,
  "streamingLongestTaskMs": 0.123,
  "retained500MessagesMemoryDeltaBytes": 637632,
  "retained500MessagesMemoryDeltaMiB": 0.60809326171875,
  "mounted500MessageRows": 11,
  "coldDashboardRenderMs": 353.039,
  "largestChunkKiB": 249.94140625,
  "unhandledPromiseRejections": 0,
  "eventLoopYielded": true
}
```

All guards are strict `<` comparisons: palette 100ms, route 300ms, streaming task 50ms, cold render 2,000ms, chunk 500KiB, and 500-message heap delta 15MiB. The runtime-health fixture processes 500 promise-delivered chunks, yields to a timer, and records zero window/process unhandled rejections.

## Contrast, axe, and reduced motion

The canonical Light muted token changed from `#667085` to `#5D6673` in both Tokens Studio JSON and runtime CSS. The `validate-tokens.mjs` contract change is limited to raising `color.text.muted / color.surface.canvas` from 4.5 to **5.0** and printing that dedicated four-accent result; no other pair, schema rule, set, theme, or alias requirement changed. The full 108-check gate was rerun:

```text
$ npm run tokens:check
Tokens Studio schema-compatible import: PASS — 12 sets, 208 tokens, 12 themes.
Contrast gate: PASS — 108 AA checks.
Light muted/canvas ≥5.0: PASS — Violet 5.47:1, Ocean 5.47:1, Forest 5.47:1, Ember 5.47:1.
  5.20:1  Dream / Warm / Forest  color.accent.text / color.surface.base
```

All five Stage D surfaces pass axe with no violations:

```text
axe_surface=sessions violations=0
axe_surface=memory violations=0
axe_surface=skills violations=0
axe_surface=subagents violations=0
axe_surface=scheduler violations=0
```

The memory run initially exposed a critical required-ARIA failure: the unavailable relevance meter omitted `aria-valuenow`. The implementation now publishes numeric fallback `0` together with human text `Unavailable`; the existing test became stricter.

Reduced motion is verified for OS and persistent app preferences. A source-policy test pins actual motion-bearing selectors for streaming, palette, dialogs, pane resize, toast, and tooltips against the global repeated-animation/transition stop rule.

```text
reduced_motion_os=PASS reduced_motion_manual=PASS
reduced_motion_surfaces=streaming,palette,dialogs,pane-resize,toast,tooltips status=PASS
```

## ESLint warning triage

Stage E temporarily observed 14 advisories versus the 11-advisory base. No suppression was added.

| New advisory                                                  | Resolution                                                                                |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `memory-score.tsx` exported pure helpers beside a component   | Extracted weights, types, and protocol-mirrored formula to tested `memory-score-model.ts` |
| `schedule-history.tsx` exported an internal status-key helper | Made the helper module-private; no external consumer existed                              |
| `status-badge.tsx` exported an internal metadata constant     | Made the constant module-private; no external consumer existed                            |

Final lint returns **0 errors / 11 advisories**. The remaining 11 are the accepted Stage C baseline: one React Compiler advisory for TanStack Table’s incompatible function-returning API and ten Fast Refresh file-boundary advisories in pre-existing shared modules. They do not affect production correctness; changing those public module boundaries is outside Stage E and no warning was hidden.

## Final gate evidence

```text
$ npm run test
Test Files  69 passed (69)
Tests       505 passed (505)

$ npm run typecheck
# exit 0

$ npm run lint
✖ 11 problems (0 errors, 11 warnings)

$ npm run format:check
All matched files use Prettier code style!

$ npm run locales:check
Locale integrity: PASS — 8 locales × 14 namespaces; 655 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=267, ja=267, es=267, de=267, fr=267, ko=267; fa gate=PASS

$ npm run storybook:build
✓ 1998 modules transformed.
✓ built in 7.14s
Ladle finished the production build in 7s producing 1.53 MiB of assets.

$ .venv/bin/pytest -q
1748 passed, 11 skipped in 61.43s (0:01:01)
```

The full outputs are appended verbatim to [`UI-GATES.md`](./UI-GATES.md). Passing Vitest retains the accepted pre-existing React `act(...)` diagnostics; no clean-stderr claim is made.

**Gate E: GREEN.**
