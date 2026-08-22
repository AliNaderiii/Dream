# UI overhaul gates A–C and senior-review resolutions

**Date:** 2026-08-22
**Branch:** `arena/01a02863-dream` (Arena fixes the session branch; it cannot be renamed to `feat/ui-overhaul-stage-abc`)
**Owners:** ARCHITEKT with LUMEN, MASON, FLUX, RÂH, VELOCITAS, AXIS, and SCRIBE

This note records command output, not projected results. Commands ran from the repository root unless an `apps/desktop` working directory is shown.

## Part 1 — red-flag investigations

### RF-1 — configuration strictness

`git log -p 143a096..HEAD -- apps/desktop/tsconfig.json apps/desktop/eslint.config.js` records one persisted net edit to each file. No second `tsconfig.json` patch exists in Git history; any transient editor operation before the Stage B commit did not survive into the repository and therefore cannot change effective configuration.

**TypeScript before → after (Stage B, retained):**

```diff
-  "include": ["src", "vite.config.ts", "eslint.config.js"],
+  "include": ["src", ".ladle/**/*.tsx", "vite.config.ts", "eslint.config.js"],
```

This increases checking scope by placing Ladle providers in the same strict TypeScript program. It does not alter `strict`, `noUnusedLocals`, `noUnusedParameters`, any `noImplicit*` setting, or an exclusion. Justification: the development-only Ladle provider is now compiled by `tsc --noEmit` instead of remaining outside the project.

**ESLint committed Stage B edit:**

```diff
-    files: ['*.config.{js,ts}', 'eslint.config.js'],
+    files: ['*.config.{js,ts}', 'eslint.config.js', '.ladle/**/*.{ts,tsx}'],
     extends: [tseslint.configs.disableTypeChecked],
```

This disabled type-aware lint for Ladle code and therefore counted as a strictness reduction. It was reverted. The final file is back to:

```js
files: ['*.config.{js,ts}', 'eslint.config.js'],
extends: [tseslint.configs.disableTypeChecked],
```

The underlying `.ladle/**/*.tsx` files pass the normal type-aware rule set. No rule was changed from error to warning/off, and no ignore was added.

Validation after revert:

```text
> tsc --noEmit
# exit 0
> eslint .
✖ 11 problems (0 errors, 11 warnings)
```

The 11 warnings are the pre-existing TanStack React Compiler and Fast Refresh diagnostics; strict lint has zero errors.

### RF-2 — locale generator integrity

A CI-able structural and interpolation audit now lives at `tools/check_locales.py` and is exposed as `npm run locales:check`. It compares namespace files, every branch/leaf JSON kind, and `{{placeholder}}` sets across all eight locales.

Final generator and integrity output:

```text
> node scripts/generate-locales.mjs
Generated 14 namespaces × 8 languages (477 keys; 534 English fallbacks).

> python ../../tools/check_locales.py
Locale integrity: PASS — 8 locales × 14 namespaces; 477 leaves and identical key/type/placeholder trees.
```

No-key-loss migration check against the Stage B `HEAD` locale output:

```text
en: before=408 after=477 added=69 lost=0
fa: before=408 after=477 added=69 lost=0
zh-CN: before=408 after=477 added=69 lost=0
ja: before=408 after=477 added=69 lost=0
es: before=408 after=477 added=69 lost=0
de: before=408 after=477 added=69 lost=0
fr: before=408 after=477 added=69 lost=0
ko: before=408 after=477 added=69 lost=0
```

The generated output was staged as the comparison baseline, regenerated, and checked for an unstaged delta:

```text
git diff --exit-code -- apps/desktop/src/locales/: PASS
```

The audit also caught and repaired an accidental English scheduler source merge (`rhythmLabel` plus `rhythmPlaceholder`) before commit. Final scheduler output has no delta from Stage B.

### RF-3 — pane stability

1. Instability came from repeatedly integrating token-stream batching, sticky-tail ownership, localized pane chrome, and Radix approval behavior in one large component; there was no intentional protocol or session-state redesign.
2. Final architecture: `Pane({ pane: PaneState, active: boolean })` owns docking/header controls; `PaneChat` owns frame-batched conversation state; recursive `SplitLayout({ node, activePaneId })` owns all pointer/keyboard resize geometry.
3. Resizing uses a measured container with 300/200 minimum constraints, keyboard separator semantics, and logical first/second ratios; RTL mirrors horizontal pointer, arrow-key, split icon, and docking-edge geometry without normalizing stored data.

Pinned regression output:

```text
✓ pins drag-resize to the measured container and minimum pane width
✓ pins keyboard resize and exposes separator value semantics
✓ mirrors horizontal pointer, keyboard, and docking geometry in RTL
Test Files  2 passed (2)
Tests       7 passed (7)
```

Pure geometry is isolated in `pane-geometry.ts` and `split-geometry.ts`; component files remain Fast Refresh compatible.

### RF-4 — existing test modifications

#### `frame-batcher.test.ts`

The only original one-line correction was a TypeScript test-shim cast, not an assertion:

```diff
-    (callback as FrameRequestCallback)(16);
+    (callback as unknown as FrameRequestCallback)(16);
```

Reason: strict TS correctly rejected direct conversion from its control-flow-narrowed `null` fixture to `FrameRequestCallback`. Runtime behavior and every original assertion remained. The test was subsequently strengthened with a `<50ms` longest-task assertion; its original checks still require zero pre-frame writes, exactly one post-frame write, all 500 tokens, and cancellation.

#### `approval-dialog.test.tsx`

The implementation contract intentionally became the stronger ARIA `alertdialog` contract:

```diff
- fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
+ fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });
  expect(onDecision).toHaveBeenCalledWith('deny');

- const dialog = screen.getByRole('dialog');
+ const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveAttribute('aria-modal', 'true');
  expect(dialog).toHaveAttribute('aria-label', 'Approval Required: write_file');
+ expect(screen.getByRole('button', { name: 'Allow once' })).toHaveFocus();
```

No assertion was weakened: Escape still must deny, `aria-modal` and accessible name remain mandatory, and initial focus plus wraparound focus-trap assertions were added. The three original callback assertions for allow once / always this session / deny remain exact.

### RF-5 — diff hygiene

No repository-wide rewrite was accepted. Prettier reported every non-target file as `(unchanged)`; the only later token-audit edits replaced explicit pixel literals in five component files with token/scale utilities. The generator is solely responsible for locale JSON and `TODO-i18n.md`.

- **Stage A (`6dcf2d1`, 25 files):** token JSON/CSS, validator, theme/store/settings integration and tests, generated settings locales, design docs, `UI-A.md`, and package scripts.
- **Stage B (`00f2bc9`, 24 files):** semantic primitives/tests, Ladle provider/config/stories, 30 snapshots, dev-only dependency lockfile, strict TypeScript inclusion, and `UI-B.md`.
- **Stage C:** command registry/search/palette/tests; shell chrome and direction-aware tooltips; pane/split geometry, streaming and tests; approval policy/dialog tests; tool cards; generated chat/common/settings locales; shell tokens and animation spec; locale checker; `UI-C.md` and this evidence note.
- **Sanctioned audit-only component edits:** comments converted from pixel prose, `memory-timeline` uses the spacing scale, `artifact-tree-view` uses standard width utilities, and `empty-state` documents a token-sized icon. No behavior or copy changed in these files.

Formatter/lint evidence:

```text
> prettier --check "src/**/*.{ts,tsx,css}"
All matched files use Prettier code style!

> eslint .
✖ 11 problems (0 errors, 11 warnings)
```

Clean-tree evidence immediately after the Stage C evidence commit:

```text
$ git status --short
# no output
PASS: working tree clean

$ git log -3 --oneline
4155015 feat(desktop): complete shell and interaction overhaul
00f2bc9 feat(desktop): rebuild semantic component library
6dcf2d1 feat(desktop): establish Rooya 2 theme foundation
```

## Part 2 — Gate evidence

## Gate A — tokens and themes

### Tokens Studio schema-compatible import

`apps/desktop/scripts/validate-tokens.mjs` is the headless plugin-equivalent gate. It requires the exact Tokens Studio schema URI, supported `$type` values/value shapes, unique themes, valid selected-set states, resolvable aliases, 12 expected theme/accent combinations, runtime CSS selectors, shell token round-trip, and contrast.

```text
> npm run tokens:check
Tokens Studio schema-compatible import: PASS — 12 sets, 208 tokens, 12 themes.
Contrast gate: PASS — 108 AA checks.
  4.68:1  Dream / Light / Violet  color.text.muted / color.surface.canvas
  4.68:1  Dream / Light / Ocean  color.text.muted / color.surface.canvas
  4.68:1  Dream / Light / Forest  color.text.muted / color.surface.canvas
  4.68:1  Dream / Light / Ember  color.text.muted / color.surface.canvas
  5.20:1  Dream / Warm / Forest  color.accent.text / color.surface.base
```

This environment cannot run the binary Figma plugin, so the accepted MP-01 alternative—the plugin-equivalent JSON/schema/import-contract check—is the executable evidence.

### Raw-value audit

```text
$ grep -RInE '[0-9]+(\.[0-9]+)?px|#[0-9A-Fa-f]{3,8}\b' \
    apps/desktop/src/components --include='*.ts' --include='*.tsx'
# no matches
PASS: 0 raw hex colors and 0 explicit px values in component TypeScript/TSX
```

There are no sanctioned component exceptions. Hex and exact dimensions live in the token layer; Tailwind spacing utilities (for example `px-3`, where `px` means padding-inline) are semantic scale references, not CSS pixel literals.

### Contrast table

Direction does not mutate color values, so the same computed ratio is independently listed for LTR and RTL. The default Violet accent table follows; the gate additionally checks all Ocean/Forest/Ember combinations for 108 total AA checks.

| Theme | Direction | Semantic pair | Ratio |
| --- | --- | --- | ---: |
| Dream / Light / Violet | LTR | color.text.primary / color.surface.base | 16.46:1 |
| Dream / Light / Violet | RTL | color.text.primary / color.surface.base | 16.46:1 |
| Dream / Light / Violet | LTR | color.text.secondary / color.surface.base | 7.10:1 |
| Dream / Light / Violet | RTL | color.text.secondary / color.surface.base | 7.10:1 |
| Dream / Light / Violet | LTR | color.text.muted / color.surface.canvas | 4.68:1 |
| Dream / Light / Violet | RTL | color.text.muted / color.surface.canvas | 4.68:1 |
| Dream / Light / Violet | LTR | color.accent.text / color.surface.base | 8.56:1 |
| Dream / Light / Violet | RTL | color.accent.text / color.surface.base | 8.56:1 |
| Dream / Light / Violet | LTR | color.accent.fg / color.accent.solid | 6.46:1 |
| Dream / Light / Violet | RTL | color.accent.fg / color.accent.solid | 6.46:1 |
| Dream / Light / Violet | LTR | color.status.success-fg / color.status.success-bg | 5.75:1 |
| Dream / Light / Violet | RTL | color.status.success-fg / color.status.success-bg | 5.75:1 |
| Dream / Light / Violet | LTR | color.status.warning-fg / color.status.warning-bg | 6.06:1 |
| Dream / Light / Violet | RTL | color.status.warning-fg / color.status.warning-bg | 6.06:1 |
| Dream / Light / Violet | LTR | color.status.danger-fg / color.status.danger-bg | 6.15:1 |
| Dream / Light / Violet | RTL | color.status.danger-fg / color.status.danger-bg | 6.15:1 |
| Dream / Light / Violet | LTR | color.status.info-fg / color.status.info-bg | 5.81:1 |
| Dream / Light / Violet | RTL | color.status.info-fg / color.status.info-bg | 5.81:1 |
| Dream / Warm / Violet | LTR | color.text.primary / color.surface.base | 14.88:1 |
| Dream / Warm / Violet | RTL | color.text.primary / color.surface.base | 14.88:1 |
| Dream / Warm / Violet | LTR | color.text.secondary / color.surface.base | 6.95:1 |
| Dream / Warm / Violet | RTL | color.text.secondary / color.surface.base | 6.95:1 |
| Dream / Warm / Violet | LTR | color.text.muted / color.surface.canvas | 5.40:1 |
| Dream / Warm / Violet | RTL | color.text.muted / color.surface.canvas | 5.40:1 |
| Dream / Warm / Violet | LTR | color.accent.text / color.surface.base | 8.37:1 |
| Dream / Warm / Violet | RTL | color.accent.text / color.surface.base | 8.37:1 |
| Dream / Warm / Violet | LTR | color.accent.fg / color.accent.solid | 6.46:1 |
| Dream / Warm / Violet | RTL | color.accent.fg / color.accent.solid | 6.46:1 |
| Dream / Warm / Violet | LTR | color.status.success-fg / color.status.success-bg | 5.65:1 |
| Dream / Warm / Violet | RTL | color.status.success-fg / color.status.success-bg | 5.65:1 |
| Dream / Warm / Violet | LTR | color.status.warning-fg / color.status.warning-bg | 5.95:1 |
| Dream / Warm / Violet | RTL | color.status.warning-fg / color.status.warning-bg | 5.95:1 |
| Dream / Warm / Violet | LTR | color.status.danger-fg / color.status.danger-bg | 6.17:1 |
| Dream / Warm / Violet | RTL | color.status.danger-fg / color.status.danger-bg | 6.17:1 |
| Dream / Warm / Violet | LTR | color.status.info-fg / color.status.info-bg | 6.06:1 |
| Dream / Warm / Violet | RTL | color.status.info-fg / color.status.info-bg | 6.06:1 |
| Dream / Dark / Violet | LTR | color.text.primary / color.surface.base | 15.97:1 |
| Dream / Dark / Violet | RTL | color.text.primary / color.surface.base | 15.97:1 |
| Dream / Dark / Violet | LTR | color.text.secondary / color.surface.base | 9.27:1 |
| Dream / Dark / Violet | RTL | color.text.secondary / color.surface.base | 9.27:1 |
| Dream / Dark / Violet | LTR | color.text.muted / color.surface.canvas | 6.65:1 |
| Dream / Dark / Violet | RTL | color.text.muted / color.surface.canvas | 6.65:1 |
| Dream / Dark / Violet | LTR | color.accent.text / color.surface.base | 10.30:1 |
| Dream / Dark / Violet | RTL | color.accent.text / color.surface.base | 10.30:1 |
| Dream / Dark / Violet | LTR | color.accent.fg / color.accent.solid | 7.48:1 |
| Dream / Dark / Violet | RTL | color.accent.fg / color.accent.solid | 7.48:1 |
| Dream / Dark / Violet | LTR | color.status.success-fg / color.status.success-bg | 7.13:1 |
| Dream / Dark / Violet | RTL | color.status.success-fg / color.status.success-bg | 7.13:1 |
| Dream / Dark / Violet | LTR | color.status.warning-fg / color.status.warning-bg | 7.64:1 |
| Dream / Dark / Violet | RTL | color.status.warning-fg / color.status.warning-bg | 7.64:1 |
| Dream / Dark / Violet | LTR | color.status.danger-fg / color.status.danger-bg | 6.43:1 |
| Dream / Dark / Violet | RTL | color.status.danger-fg / color.status.danger-bg | 6.43:1 |
| Dream / Dark / Violet | LTR | color.status.info-fg / color.status.info-bg | 6.13:1 |
| Dream / Dark / Violet | RTL | color.status.info-fg / color.status.info-bg | 6.13:1 |

### Warm theme coverage

Every Ladle story is wrapped by `ThemeMatrix`, whose 12 cells include `warm/ltr/comfortable`, `warm/ltr/dense`, `warm/rtl/comfortable`, and `warm/rtl/dense`. Warm is explicitly asserted by `theme-matrix.test.tsx`. Story names: Buttons, Badges, Inputs, Cards, Skeletons, Dialogs, Dropdowns, Tooltips, TabSets, Switches, Toasts, EmptyStates, and CommandPalettes.

## Gate B — component library

### Ladle catalog and matrix

The production catalog built successfully:

```text
> npm run storybook:build
✓ built in 6.98s
✓ Meta.json successfully created.
⏱️ Ladle finished the production build in 7s producing 1.48 MiB of assets.
```

Built story groups and matrix axes:

| Story/component group | Themes | Directions | Densities | Cells |
| --- | --- | --- | --- | ---: |
| Buttons | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Badges | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Inputs + Textarea | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Cards | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Skeletons | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Dialogs | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Dropdowns | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Tooltips | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| TabSets | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Switches | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| Toasts | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| EmptyStates | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |
| CommandPalettes | Light / Warm / Dark | LTR / RTL | Comfortable / Dense | 12 |

Ladle is development-only. The top 30 primitive states remain committed as DOM visual-regression snapshots.

```text
✓ Rooya component visual contracts > commits exactly the top 30 primitive states
✓ Ladle theme matrix > covers three themes, two directions, and two densities
Test Files  3 passed (3)
Tests       33 passed (33)
```

### Full Vitest regression

```text
command_palette_open_ms=60.309 budget_ms=100
axe_critical_violations=0 axe_total_violations=0
stream_fixture_tokens=500 writes=1 longest_task_ms=0.124
Test Files  53 passed (53)
Tests       439 passed (439)
```

The 439 passing tests exceed the stated 345-test baseline and the post-Stage-B 415-test count. Failed: 0.

### axe-core

```text
axe_critical_violations=0 axe_total_violations=0
Test Files  3 passed (3)
Tests       33 passed (33)
```

Color contrast is disabled only in jsdom axe runs because jsdom has no paint engine; the separate token gate computes 108 WCAG ratios.

## Gate C — shell and signature surfaces

### Command palette

The hot path is local-only and synchronous; no bridge or network work occurs on open.

```text
command_palette_open_ms=60.309 budget_ms=100
✓ opens the local command palette within the perceived-interaction budget
```

Keyboard coverage:

```text
✓ opens the command palette with the keyboard and runs a command
✓ completes the keyboard-only type, arrow, enter, reopen, and Escape walkthrough
✓ supports arrows, Home, End, and Enter from the focused input
✓ allows the palette shortcut while an editor has focus
```

Search normalizes Persian/Arabic presentation variants, ranks stable subsequences, and filters a 1,000-command fixture in 3ms in the targeted run.

### Streaming path

The 500-token fixture schedules one animation frame and one store write; pending work is cancellable. Measured test tasks:

```text
stream_fixture_tokens=500 writes=1 longest_task_ms=0.124
✓ coalesces any token count into one write per frame
✓ can cancel pending output
```

`PaneChat` scrolls only when its sticky-tail ownership ref is true, stops following when the reader leaves the 64-unit threshold, schedules `scrollIntoView` in animation frames, and uses `content-visibility: auto` for settled transcript rows. Reduced-motion selectors remove the translated sweep without changing state semantics.

### LTR/RTL shell and pane geometry

```text
✓ switches the document to RTL for Persian
✓ pins drag-resize to the measured container and minimum pane width
✓ pins keyboard resize and exposes separator value semantics
✓ mirrors horizontal pointer, keyboard, and docking geometry in RTL
```

The shell assertion verifies `border-e` remains logical in both directions and rejects physical `border-l`/`border-r`. The split tests verify mirrored pointer coordinates and arrow keys. Direction changes update the document `dir`/`lang` attributes without remounting normalized data.

### Approval dialog

```text
✓ calls onDecision("allow_once") when Allow once is clicked
✓ calls onDecision("allow_always_session") when Always allow is clicked
✓ calls onDecision("deny") when Deny is clicked
✓ calls onDecision("deny") on Escape key
✓ renders the generated Persian approval choices
✓ uses modal alertdialog semantics, begins on allow once, and traps focus
✓ wires allow_once to approval.resolve allowed=true
✓ wires allow_always_session to approval.resolve allowed=true
✓ wires deny to approval.resolve allowed=false
```

The alert dialog is Radix focus-trapped, explicitly modal, initially focuses Allow once, wraps Tab/Shift+Tab, and fails closed on Escape/outside dismissal. Arguments are selectable and direction-isolated. Both English and Persian choices come from generated locale trees.

## Cross-cutting regression gates

### Python

The base interpreter initially lacked pytest. A disposable ignored `.venv` was created from the repository's `.[dev]` extra; no dependency or lockfile changed.

```text
$ PATH="$PWD/.venv/bin:$PATH" python -m pytest
================= 1748 passed, 11 skipped in 65.74s (0:01:05) ==================
```

This exactly matches the required baseline.

### Desktop static checks and builds

```text
$ npm run typecheck
> tsc --noEmit
# exit 0

$ npm run lint
✖ 11 problems (0 errors, 11 warnings)

$ npm run format:check
All matched files use Prettier code style!

$ npm run build
✓ built in 5.75s

$ npm run storybook:build
✓ built in 6.98s
✓ Meta.json successfully created.
Ladle finished the production build in 7s producing 1.48 MiB of assets.
```

Vite retains its pre-existing advisory that the main minified chunk exceeds 500kB; the build exits 0. Performance chunking is an explicit Stage E budget item and was not hidden by changing the warning threshold.

### Kernel and protocol boundary

```text
$ git diff --stat -- dream/ tests/
# no output
PASS: no changes under dream/ or tests/
```

No Python kernel, JSON-RPC protocol, metering, or ledger file changed.

## Gate decision

**Stages A, B, and C: GREEN.** All mandatory red flags have executable resolutions; token/theme, component, shell, command, streaming, directionality, approval, localization, build, TypeScript, lint, formatting, Vitest, and Python gates pass. Stage D may begin only after this note and `UI-C.md` are committed and the PR is opened from the Arena-fixed branch.

---

# Gate D — operational workspaces

Full implementation and RF-4 assertion rationale: [`UI-D.md`](./UI-D.md).

## Lifecycle and bounded rendering

All five surfaces have executable empty, loading (at least three skeletons), actionable retry, and bridge-dead/reconnect coverage. Pending work is renderer-timeout/AbortSignal bounded. Memory and scheduler test superseded requests; sessions, skills, and subagents test unmount cancellation and spinner removal.

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

The memory explainability widget pins `0.55 × relevance + 0.20 × recency + 0.15 × importance + 0.10 × usage`, four accessible meters, weighted total, unavailable relevance, and Persian RTL labels. Skills and memory unstable logic is extracted into pure, unit-tested models. The subagent route exposes status/limits, pause/resume/cancel RPC wiring, virtualized tailing, and proposer/critic/judge council with winner strip. Scheduler coverage pins English and Persian input, cron, exactly three Gregorian/Jalali rows, virtualized history, and fail-closed approval denial reasons.

## Final desktop suite

```text
$ npm run test
command_palette_open_ms=54.521 budget_ms=100
session_fixture_rows=1000 mounted_rows=26
memory_fixture_rows=1000 mounted_rows=8
skills_fixture_rows=1000 mounted_rows=10
subagent_log_rows=1000 mounted_rows=5
scheduler_history_rows=1000 mounted_rows=26
Test Files  62 passed (62)
Tests       484 passed (484)
```

## Static, token, locale, and build gates

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

$ npm run build
✓ 2039 modules transformed.
✓ built in 5.25s

$ npm run storybook:build
✓ 1998 modules transformed.
✓ built in 13.21s
✓ Meta.json successfully created.
Ladle finished the production build in 14s producing 1.53 MiB of assets.
```

Vite's >500kB advisory remains visible and its threshold is unchanged. Stage E owns route splitting/lazy panes.

## Python and protected paths

```text
$ .venv/bin/pytest -q
1748 passed, 11 skipped in 59.86s

$ git diff --stat -- dream/ tests/
# no output
protected_paths=dream/,tests/ unchanged

$ git diff --check
diff_check=PASS
```

## Gate decision

**Stage D: GREEN.** Session manager, memory explorer, skills manager, subagent dashboard, scheduler UI, cancellation/timeout behavior, lifecycle states, virtualization, bilingual/RTL semantics, regression suites, and protected-path boundaries pass. Stage E may proceed from the Arena-fixed branch `arena/01a02863-dream`.

---

# Gate E — performance, bundle, and accessibility

Full implementation and R4-1 assertion audit: [`UI-E.md`](./UI-E.md).

## Production bundle

The existing Vite 500kB warning threshold is unchanged. Stage D emitted one 1,006.32kB / 313.01kB-gzip entry and printed the large-chunk advisory. Stage E resolves that graph through lazy routes, a nested lazy pane workspace, on-demand locale resources, and explicit React/UI/i18n vendor chunks.

```text
$ npm run build
vite v7.3.6 building client environment for production...
✓ 2044 modules transformed.
dist/assets/pane-workspace-Cf2TMdji.js  28.77 kB │ gzip:  9.72 kB
dist/assets/i18n-vendor-CkSKoGz1.js    49.67 kB │ gzip: 16.37 kB
dist/assets/ui-vendor-Cb0Ln_mG.js      76.66 kB │ gzip: 24.94 kB
dist/assets/index-BScXyVnd.js         203.78 kB │ gzip: 63.22 kB
dist/assets/react-vendor-BSOuYUyy.js  255.94 kB │ gzip: 83.25 kB
✓ built in 5.00s
```

Every production app JavaScript chunk is below 500kB uncompressed. The entry is 63.22kB gzip, below 250kB. No >500kB advisory is emitted by the app build.

Ladle is a development-only tooling graph containing its own axe/runtime code; it uses `.ladle/vite.config.mjs` rather than the Tauri app's production vendor partition so story-tool dependencies do not create circular chunks.

## JSON performance budgets

```text
$ npm run performance:check
{
  "schemaVersion": 1,
  "budgets": {
    "paletteOpenMs": 100,
    "routeChangeMs": 300,
    "streamingLongestTaskMs": 50,
    "retained500MessagesMiB": 15,
    "coldStartMs": 2000,
    "maxChunkKiB": 500
  },
  "measurements": {
    "paletteOpenMs": 52.125,
    "routeChangeMs": 168.487,
    "streamingLongestTaskMs": 0.123,
    "retained500MessagesMemoryDeltaBytes": 637632,
    "retained500MessagesMemoryDeltaMiB": 0.60809326171875,
    "serialized500MessagesBytes": 567531,
    "mounted500MessageRows": 11,
    "coldDashboardRenderMs": 353.039,
    "coldAssetReadMs": 0.6367719999998371,
    "maximumRouteAssetReadMs": 1.226571999999578,
    "largestChunkBytes": 255940,
    "largestChunkKiB": 249.94140625,
    "largestChunkFile": "react-vendor-BSOuYUyy.js",
    "unhandledPromiseRejections": 0,
    "eventLoopYielded": true
  },
  "pass": true
}
```

`apps/desktop/scripts/perf-check.ts` emits and writes this JSON. The Arena GitHub App cannot update workflow files, so [`ci-perf-check.patch`](./ci-perf-check.patch) carries the owner-applied Desktop CI steps that build the app, run the guard, and upload `apps/desktop/performance-results.json` as `desktop-performance-${{ github.sha }}`. The harness lands here; workflow application is explicitly deferred to an owner.

## Variable-height transcript virtualization

```text
chat_fixture_rows=120 mounted_message_rows=11
message_fixture_rows=500 mounted_message_rows=11
variable_fixture_rows=1000 mounted_rows=15
✓ releases tail ownership after the reader scrolls away
```

The newest row is rendered on initial chat mount. Settled and active streaming rows share the bounded feed. Pure `pane-chat-model.ts` and `variable-virtual-geometry.ts` tests pin ordering, non-mutation, offset/range calculations, and sticky-tail release.

## Contrast

```text
$ npm run tokens:check
Tokens Studio schema-compatible import: PASS — 12 sets, 208 tokens, 12 themes.
Contrast gate: PASS — 108 AA checks.
Light muted/canvas ≥5.0: PASS — Violet 5.47:1, Ocean 5.47:1, Forest 5.47:1, Ember 5.47:1.
  5.20:1  Dream / Warm / Forest  color.accent.text / color.surface.base
```

The token source and runtime CSS both use `#5D6673`; the validator enforces 5.0 for the muted/canvas pair.

## axe and reduced motion

```text
$ npm run accessibility:check
axe_surface=sessions violations=0
axe_surface=memory violations=0
axe_surface=skills violations=0
axe_surface=subagents violations=0
axe_surface=scheduler violations=0
reduced_motion_os=PASS reduced_motion_manual=PASS
reduced_motion_surfaces=streaming,palette,dialogs,pane-resize,toast,tooltips status=PASS
Test Files  3 passed (3)
Tests       9 passed (9)
```

jsdom axe disables only color contrast because jsdom cannot paint. The separate token resolver performs the 108 color checks. The all-five-surface axe run found one real critical issue during development—the unavailable memory meter omitted required `aria-valuenow`—which was fixed and given a stricter assertion before the final zero-violation run.

## Final desktop suite

```text
$ npm run test
cold_dashboard_render_ms=366.748 budget_ms=2000
warm_route_change_ms=172.624 budget_ms=300
command_palette_open_ms=44.412 budget_ms=100
session_fixture_rows=1000 mounted_rows=26
memory_fixture_rows=1000 mounted_rows=8
skills_fixture_rows=1000 mounted_rows=10
subagent_log_rows=1000 mounted_rows=5
scheduler_history_rows=1000 mounted_rows=26
chat_fixture_rows=120 mounted_message_rows=11
message_fixture_rows=500 mounted_message_rows=11
variable_fixture_rows=1000 mounted_rows=15
stream_fixture_tokens=500 writes=1 longest_task_ms=0.120
stream_runtime_chunks=500 event_loop_yielded=true unhandled_rejections=0
Test Files  69 passed (69)
Tests       505 passed (505)
Duration    120.15s
```

The suite exceeds the Stage D 484-test baseline. As in the accepted Stage D run, passing Vitest emits existing React `act(...)` diagnostics from background/Radix updates; no clean-stderr claim is made.

## TypeScript, lint, formatting, and locales

```text
$ npm run typecheck
> tsc --noEmit
# exit 0

$ npm run lint
✖ 11 problems (0 errors, 11 warnings)

$ npm run format:check
All matched files use Prettier code style!

$ npm run locales:check
Locale integrity: PASS — 8 locales × 14 namespaces; 655 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=267, ja=267, es=267, de=267, fr=267, ko=267; fa gate=PASS
```

The warning count returned from the transient 14 to the accepted 11 baseline with no suppression: memory score logic was extracted to a pure model, and two internal scheduler/subagent values stopped being exported. The remaining advisories are one TanStack/React-Compiler compatibility notice and ten pre-existing Fast Refresh file-boundary notices.

## Ladle

```text
$ npm run storybook:build
vite v6.4.3 building for production...
✓ 1998 modules transformed.
✓ built in 7.14s
✓ Meta.json successfully created.
Ladle finished the production build in 7s producing 1.53 MiB of assets.
```

## Python and protected paths

Pytest ran by itself, with no concurrent frontend or Ladle build. The CI comment records the known Telegram polling timing sensitivity and keeps Python jobs isolated from build work.

```text
$ .venv/bin/pytest -q
1748 passed, 11 skipped in 61.43s (0:01:01)

$ git diff --stat -- dream/ tests/
# no output
protected_paths=dream/,tests/ unchanged

$ git diff --check
# no output
diff_check=PASS
```

## Gate E decision

**Stage E: GREEN.** App bundle, entry gzip, palette, route, streaming task, retained memory, runtime health, transcript virtualization, contrast, axe, reduced motion, full desktop/Python suites, static checks, locale integrity, Ladle, executable artifact harness, owner-applicable CI patch, test-edit audit, and protected boundaries pass.

---

# Gate F — design handoff and close-out

## Required documents

```text
$ test -f docs/design/visual-language.md \
    -a -f docs/design/figma-handoff.md \
    -a -f docs/design/accessibility-audit-v2.md \
    -a -f docs/handoff/UI-E.md \
    -a -f docs/handoff/UI-F.md \
    -a -f docs/handoff/ci-perf-check.patch && echo 'stage_f_documents=PASS'
stage_f_documents=PASS
```

- `visual-language.md` records calm/precise/trustworthy direction, three-theme rationale, motion philosophy, and explicit restraint.
- `figma-handoff.md` records exact Tokens Studio import/export steps, 12 ordered sets, 12 theme combinations, ownership, and token proposal rules.
- `accessibility-audit-v2.md` compares prototype/pre-Stage-E findings with implemented contrast, keyboard, ARIA, RTL, reduced-motion, axe, and virtualization evidence, while retaining honest native assistive-technology follow-ups.
- `UI-F.md` contains the source-rendered screenshot/reference manifest and Definition-of-Done map.
- `ci-perf-check.patch` contains the exact deferred workflow diff for owner application; the Arena App cannot write either workflow file.

## Truthful product records

`MASTER_CHECKLIST.md` marks conversation, session manager, skills, and subagent dashboard complete. The combined memory/reminder item stays open because reminder authoring is absent. The combined scheduler-edit item stays open because a full existing-schedule edit flow is absent. `CHANGELOG.md` and the README describe only shipped desktop behavior and executable commands.

## Screenshot/reference policy

No binary design asset was added. The reproducible references are the token-driven Phase-0 prototype, Ladle primitive and theme matrices, committed DOM snapshots, and route/state fixtures listed in `UI-F.md`.

## Orchestrator-level diff review

```text
branch=arena/01a02863-dream
protocol_changes=0
protected_paths=dream/,tests/ unchanged
telemetry_or_analytics_added=0
raw_component_hex_or_px_added=0
diff_check=PASS
```

Review findings:

- all seven Stage E/F specialist scopes reached their focused and full gates;
- every changed existing assertion is documented in `UI-E.md`; no test was skipped or weakened;
- `bridge.test.ts` remains unchanged from accepted Gate D;
- pane and variable-list regression churn moved into pure tested models;
- route skeletons have three structural states and use no hardcoded user-facing text;
- token JSON and runtime CSS agree;
- locale trees and Persian fallback count are unchanged and green;
- production code adds no network call, runtime dependency, telemetry, analytics, protocol, kernel, metering, or ledger change;
- R5-1 Path B is active: direct pushes failed first on `.github/workflows/ci.yml` and then on `.github/workflows/desktop-ci.yml` because the Arena App lacks `workflows` permission. Both workflows remain at the accepted remote base, and `ci-perf-check.patch` preserves their exact intended diff for owner application.

## Gate F decision

**Stage F: GREEN.** Design, Tokens Studio, accessibility, screenshot/reference, checklist, changelog, README, cumulative evidence, owner-applied CI patch, and orchestrator review deliverables are complete. Gates A–F are closed on the Arena-fixed branch; native screen-reader/forced-colors checks and owner workflow patch application remain explicitly documented release-environment verification rather than being falsely claimed by jsdom or the restricted GitHub App.
