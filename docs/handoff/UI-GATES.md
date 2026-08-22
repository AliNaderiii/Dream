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
