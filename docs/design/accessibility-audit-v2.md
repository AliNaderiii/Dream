# Dream accessibility audit v2 — implemented desktop

- **Audit date:** 2026-08-22
- **Standard:** WCAG 2.1 AA
- **Scope:** Tauri 2 / React desktop shell, with executable jsdom, token, locale, and source-policy gates
- **Baseline:** [`accessibility-audit.md`](./accessibility-audit.md), which audited the Phase-0 prototype

## Executive result

The implemented desktop passes the automated acceptance scope:

- 108/108 semantic contrast checks pass; Light muted text on canvas is 5.47:1 for all four accents.
- axe-core reports zero violations, including zero critical violations, on sessions, memory, skills, subagents, and scheduler.
- runtime tests cover keyboard navigation, focus-trapped approval, route and command-palette interaction, Persian RTL, and mixed-direction content.
- OS and in-app reduced-motion paths stop repeated animation and make transitions effectively immediate; representative coverage includes streaming, palette, dialogs, pane resize, toast, and tooltips.
- the locale gate reports `fa=0` English fallbacks with identical key/type/placeholder trees across eight locales.

Color contrast is disabled only inside jsdom axe runs because jsdom has no paint engine. `npm run tokens:check` independently computes contrast from the canonical token graph.

## Before/after findings

| Area                      | Phase-0 / pre-Stage-E evidence                                                                           | Implemented v2 evidence                                                                                                                                                                                                          | Result                             |
| ------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| Light muted contrast      | Prototype audit corrected muted text to about 4.71:1; Stage-A token gate later measured 4.68:1 on canvas | `#5D6673` measures 5.47:1 on Light canvas for Violet, Ocean, Forest, and Ember; validator minimum is now 5.0 for the muted/canvas pair                                                                                           | Improved beyond the Stage-E target |
| General semantic contrast | Prototype table was manually scoped to representative pairs                                              | Token resolver validates aliases for 12 themes and executes 108 AA checks covering primary, secondary, muted, accent, and four status pairs                                                                                      | Automated and broader              |
| Keyboard operation        | Key map and focus behavior were design specifications                                                    | Tests exercise command palette open/search/arrows/Home/End/Enter/Escape, keyboard-only walkthrough, sidebar/session creation, pane separator semantics, RTL resize geometry, and approval focus trapping                         | Implemented                        |
| Approval semantics        | Prototype specified an alert dialog and safe Escape behavior                                             | Radix alert dialog is modal, labelled, focus-trapped, starts on Allow once, wraps Tab/Shift+Tab, and maps Escape/outside dismissal to Deny                                                                                       | Implemented, fail closed           |
| ARIA state                | Prototype described live regions and labelled status                                                     | axe found an unranked memory meter missing required `aria-valuenow`; implementation now exposes `aria-valuenow="0"` with `aria-valuetext="Unavailable"`. All five audited surfaces then reached zero violations                  | Defect found and fixed             |
| Streaming                 | Prototype specified polite announcement and reduced caret/sweep                                          | Active virtualized row uses polite live semantics and busy state; frame batching keeps 500 chunks to one write; reduced motion stops the sweep                                                                                   | Implemented and bounded            |
| RTL                       | Prototype toggle and checklist verified layout intent                                                    | App-level Persian switch sets `dir="rtl"`/`lang="fa"`; shell, pane split/docking, score labels, Jalali cells, and logical borders have runtime assertions                                                                        | Implemented                        |
| Mixed direction           | Prototype relied on LTR-island classes                                                                   | Runtime uses logical properties plus `unicode-bidi: isolate`; code, cron, paths, metrics, and normalized data remain direction-safe                                                                                              | Implemented                        |
| Reduced motion            | Prototype declared global duration collapse                                                              | Both `prefers-reduced-motion` and persistent `data-reduce-motion="true"` enforce automatic scrolling, one animation iteration, and 0.01ms animation/transition durations. Six representative motion surfaces are source-verified | Implemented                        |
| Zoom/density/theme        | Prototype offered a subset of matrix toggles                                                             | Persistent theme, accent, direction, comfortable/dense mode, 80–150% zoom, numeral style, and motion preference are applied as one document appearance snapshot; Ladle renders 3 themes × 2 directions × 2 densities             | Implemented                        |
| Long operational lists    | Prototype did not prove bounded accessibility-tree size                                                  | Sessions, scheduler history, memory, skills, subagent logs, and chat messages virtualize at 100+ rows; measured fixtures stay below 60 mounted rows                                                                              | Implemented                        |

## axe-core surface matrix

Command: `cd apps/desktop && npm run accessibility:check`

| Surface            | Settled state audited                   | Critical violations | Total violations |
| ------------------ | --------------------------------------- | ------------------: | ---------------: |
| Session manager    | Empty session state in shell navigation |                   0 |                0 |
| Memory explorer    | Loaded explainable-memory cards         |                   0 |                0 |
| Skills manager     | Loaded installed/registry cards         |                   0 |                0 |
| Subagent dashboard | Empty operational dashboard             |                   0 |                0 |
| Scheduler          | Empty schedule workspace                |                   0 |                0 |

The tests use the real surface components and generated English resources. Lifecycle-specific tests separately cover empty, at least three loading skeletons, actionable error/retry, offline/reconnect, and settlement after cancellation.

## Contrast results

`npm run tokens:check` resolves every selected Tokens Studio set before calculating relative luminance.

| Requirement                           | Measured result |
| ------------------------------------- | --------------: |
| Light muted / canvas, Violet          |          5.47:1 |
| Light muted / canvas, Ocean           |          5.47:1 |
| Light muted / canvas, Forest          |          5.47:1 |
| Light muted / canvas, Ember           |          5.47:1 |
| Normal semantic text floor            |          ≥4.5:1 |
| Light muted Stage-E floor             |          ≥5.0:1 |
| Total checked theme/pair combinations |             108 |

The lowest overall checked pair after the change is Warm/Forest accent text on base at 5.20:1.

## Keyboard and focus verification

Automated coverage confirms:

- `Ctrl/⌘K` opens the local command palette without bridge work; Escape closes it.
- Search input supports arrow movement, Home, End, Enter, and Persian text normalization.
- Session creation is keyboard-accessible and navigation waits for the bounded bridge result.
- Pane separator exposes separator role/value semantics and mirrored keyboard geometry in RTL.
- Approval choices are reachable in a trapped cycle; Escape and outside dismissal deny rather than allow.
- Retry and reconnect controls are named buttons, not click-only cards.
- Virtualized rows retain semantic item position/set size where relevant, while focusable content remains mounted only in the active range.

## RTL and localization verification

- Persian is loaded as an installed locale with no English fallback for Stage A–D keys.
- Document language and direction change together without remounting or mutating persisted data.
- Components use inline/block logical properties; tests reject physical border-left/right on the shell edge.
- Horizontal pane pointer, arrow-key, and docking geometry mirror.
- Memory factor labels are real Persian strings; scheduler preview renders exactly three Jalali cells with Persian digits alongside locale-formatted Gregorian values.
- LTR islands preserve code, model names, paths, cron, and metrics inside Persian prose.

## Reduced-motion verification

The global policy applies to every descendant and pseudo-element, so component authors do not need one-off suppression rules. Executable representative checks pin the motion-bearing selectors for:

1. active streaming sweep;
2. command palette overlay/content;
3. dialogs;
4. pane resize affordance;
5. toast entry;
6. tooltip entry.

Both OS preference and the persisted in-app setting set scrolling to `auto`, animation duration to 0.01ms, animation iteration count to one, and transition duration to 0.01ms. Information and controls remain present when motion stops.

## Remaining manual verification

These items require real assistive technology or OS rendering and are not falsely claimed by jsdom:

- NVDA and Narrator pass in the Windows WebView2 production build, including Persian pronunciation.
- VoiceOver pass on a signed macOS build when macOS distribution is enabled.
- Windows forced-colors/high-contrast visual review.
- 400% platform zoom and screen-magnifier review in the native Tauri window.

They are release-environment checks, not known automated failures. The repository gates prevent regressions in semantics, contrast tokens, directionality, motion policy, and keyboard contracts in the meantime.

## Source-rendered references

No binary screenshot is the design source of truth. Reviewers can reproduce the audited states from:

- [`prototype/index.html`](./prototype/index.html) — original Phase-0 comparison reference;
- `apps/desktop/src/stories/ui.stories.tsx` — primitive/state catalog;
- `apps/desktop/src/stories/theme-matrix.tsx` — Light/Warm/Dark × LTR/RTL × comfortable/dense;
- `apps/desktop/src/routes/stage-d-accessibility.test.tsx` — five-surface axe fixtures;
- [`../handoff/UI-F.md`](../handoff/UI-F.md) — final reference manifest and gate close-out.
