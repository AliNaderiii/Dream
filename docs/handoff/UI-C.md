# UI Stage C handoff — shell and signature surfaces

**Date:** 2026-08-22
**Owners:** FLUX / RÂH / VELOCITAS / AXIS, orchestrated by ARCHITEKT
**Status:** Gate green; full evidence is in [`UI-GATES.md`](./UI-GATES.md).

## Delivered

- Rebuilt the command palette as a complete local registry for actions, routes/workbenches, live sessions, theme/accent/density/zoom/motion preferences, and all eight locales.
- Added English/Persian-safe fuzzy normalization, stable subsequence ranking, grouping, combobox/listbox semantics, pointer selection, and Arrow/Home/End/Enter/Escape behavior.
- Added frame-coalesced conversation streaming, cancellation of stale visual batches, sticky-tail scroll ownership, reduced-motion-safe sweep light, content visibility for settled transcript rows, and localized pane chrome.
- Rebuilt tool-call status cards with localized disclosures, direction-isolated technical content, calm running/success/error/blocked states, and screen-reader status announcements.
- Rebuilt approval as a focus-trapped modal `alertdialog`; Allow once receives initial focus, Escape/outside fail closed, and all three decisions map explicitly to `approval.resolve`.
- Added accessible pointer/keyboard split resizing and mirrored horizontal pointer, arrow-key, icon, tooltip, and docking geometry in RTL.
- Polished shell surface layering, semantic title/status dimensions, direction-aware rail tooltips, and background-work traveling light.
- Expanded the motion specification with timing tiers, FLIP constraints, one-frame streaming writes, reduced-motion behavior, and no-layout-thrash rules.
- Added locale/tree and Tokens Studio schema-compatible gates; regenerated identical 477-leaf trees for eight locales with 534 explicit English fallbacks recorded in `TODO-i18n.md`.

## Decisions

1. Command search remains synchronous and local. Opening the palette never waits on a bridge/network request; registry changes are memoized from local stores.
2. Streaming tokens are visual deltas only. The final bridge reply is authoritative, so pending token batches are cancelled before finalization or failure.
3. Reader scroll ownership wins over streaming. Following stops when the user leaves the tail threshold and resumes only after they return.
4. The internal layout store retains normalized first/second split ordering. Component geometry converts physical RTL input to that logical representation.
5. Pane default screen names are rendered from locale keys rather than persisted English defaults; user-renamed values remain unchanged.
6. The Stage B ESLint exception for Ladle was reverted. Ladle now passes the normal type-aware lint program.
7. No bridge protocol, Python kernel, metering, ledger, or runtime dependency changed.

## Key files

- `src/components/shared/command-search.ts`, `command-palette.tsx`, and tests
- `src/hooks/use-keyboard-shortcuts.ts` and test
- `src/lib/performance/frame-batcher.ts` and test
- `src/components/panes/pane.tsx`, `split-layout.tsx`, geometry modules, and split regression test
- `src/components/chat/tool-card.tsx`, `approval-dialog.tsx`, `approval-policy.ts`, and tests
- `src/components/layout/{activity-rail,app-shell,status-bar,title-bar,top-bar}.tsx`
- `scripts/generate-locales.mjs`, generated locale trees, and `tools/check_locales.py`
- `scripts/validate-tokens.mjs`, canonical token JSON/CSS, and runtime theme mapping
- `docs/design/animation-specs.md`
- `docs/handoff/UI-GATES.md`

## Gate evidence summary

```text
Tokens Studio schema-compatible import: PASS — 12 sets, 208 tokens, 12 themes.
Contrast gate: PASS — 108 AA checks.
Locale integrity: PASS — 8 locales × 14 namespaces; 477 leaves and identical key/type/placeholder trees.
Raw component values: 0 hex colors; 0 explicit px values.
Vitest: 53 files, 439 passed, 0 failed.
Python: 1748 passed, 11 skipped.
TypeScript: exit 0.
ESLint: 0 errors (11 pre-existing warnings).
Prettier: all files matched.
Vite: built in 5.75s.
Ladle: built in 6.98s; 1.48 MiB development-only catalog.
Command palette open: 60.309ms (<100ms).
500-token stream: 1 write; longest measured task 0.124ms (<50ms).
axe-core: 0 critical, 0 total violations in the representative primitive gate.
```

## Regression notes

- Existing full-shell tests still emit non-fatal React `act(...)` diagnostics from asynchronous legacy route/provider effects. Counts did not increase test failures; all 439 tests pass.
- Vite still reports the existing advisory for a minified main chunk over 500kB. The threshold was not hidden or weakened; route/chunk budgets remain Stage E work.
- Binary Figma cannot run in this headless environment. The accepted plugin-equivalent Tokens Studio schema/import/alias/runtime round-trip gate is executable and green.

## Exact diff summary
Before commit, `git diff --cached --stat`: **69 files changed, 3,280 insertions, 386 deletions**.
