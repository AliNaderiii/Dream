# Dream design system — Rooya 2

**Version 2.0 · 2026-08-22**  
Runtime: Tauri 2 · React 19 · Tailwind CSS 4 · Shadcn-mappable primitives · Lucide

The source of truth is [`tokens/dream.tokens.json`](tokens/dream.tokens.json). [`tokens/dream.css`](tokens/dream.css) is its reviewed runtime export and is imported directly by the desktop app. See [`visual-language.md`](visual-language.md) for emotional direction.

## 1. Token architecture

Rooya has three layers:

1. **Core:** neutral and accent primitives, spacing, shape, typography, motion, z-index, density.
2. **Semantic:** Light / Warm / Dark mappings such as `color.surface.raised`, `color.text.secondary`, and `color.status.danger-fg`.
3. **Accent:** Violet / Ocean / Forest / Ember mappings such as `color.accent.solid`, `color.accent.fg`, and `color.accent.focus`.

Components consume semantic aliases only. The Tokens Studio file contains 12 selectable combinations (3 themes × 4 accents), uses DTCG `$type`/`$value`, and declares `$themes` plus `$metadata.tokenSetOrder` for round-trip import.

Runtime attributes:

```html
<html data-theme="warm" data-accent="forest" data-density="dense" dir="rtl">
```

`system` is an application preference, not a fourth theme: it resolves to Light or Dark. Warm is always explicit.

## 2. Semantic color contract

| Token | Purpose |
| --- | --- |
| `color.surface.canvas` | window and route background |
| `color.surface.base` | panes, cards, controls |
| `color.surface.raised` | elevated cards and sticky chrome |
| `color.surface.subtle` | nested regions and hover states |
| `color.surface.sunken` | code/log/input wells |
| `color.surface.overlay` | dialogs, menus, popovers |
| `color.text.primary` | primary copy |
| `color.text.secondary` | labels and supporting copy |
| `color.text.muted` | timestamps and placeholders |
| `color.accent.solid` | primary action and active marker |
| `color.accent.fg` | text/icon on solid accent |
| `color.accent.text` | links and selected labels |
| `color.border.subtle/strong` | separators / control emphasis |
| `color.status.*` | icon + label + background status sets |

### Measured contrast (default Violet)

Ratios are identical in LTR/Inter and RTL/Vazirmatn because script changes no color. `npm run tokens:check` verifies all **108** required pairs across 12 theme/accent combinations.

| Theme | Script | Primary/base | Secondary/base | Muted/canvas | Accent text/base | Accent fg/solid |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Light | Latin / LTR | 16.46 | 7.10 | 4.68 | 8.56 | 6.46 |
| Light | Persian / RTL | 16.46 | 7.10 | 4.68 | 8.56 | 6.46 |
| Warm | Latin / LTR | 14.88 | 6.95 | 5.40 | 8.37 | 6.46 |
| Warm | Persian / RTL | 14.88 | 6.95 | 5.40 | 8.37 | 6.46 |
| Dark | Latin / LTR | 15.97 | 9.27 | 6.65 | 10.30 | 7.48 |
| Dark | Persian / RTL | 15.97 | 9.27 | 6.65 | 10.30 | 7.48 |

Normal text must be ≥4.5:1; large text and non-text UI ≥3:1. Focus indicators use a 2px-equivalent ring plus 2px-equivalent surface offset. Status meaning always includes icon and text.

## 3. Typography

| Role | Size | Latin leading | Persian leading | Weight |
| --- | ---: | ---: | ---: | ---: |
| Display | 1.875rem | 1.3 | 1.3 | 700 |
| H1 | 1.5rem | 1.3 | 1.35 | 650 |
| H2 | 1.25rem | 1.3 | 1.4 | 650 |
| H3 | 1rem | 1.3 | 1.5 | 600 |
| Body | 0.875rem | 1.57 | **1.72** | 400/500 |
| Body large | 1rem | 1.625 | **1.75** | 400 |
| Caption | 0.75rem | 1.5 | 1.7 | 500 |
| Micro | 0.6875rem | 1.45 | 1.7 | 600 |

- LTR: `Inter Variable, Inter, system-ui`.
- RTL: `Vazirmatn Variable, Vazirmatn, Tahoma`; Inter remains the Latin fallback.
- Code/data: JetBrains Mono, LTR, isolated, tabular numerals.
- UI zoom applies root scale from 80–150%; dimensions are rem-based.
- Persian numeral display is opt-in and never mutates normalized values.

## 4. Space, density, radius, elevation

Spacing follows a 4px-equivalent base in rem: `0, 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, 64`. Use named tokens, not one-off component values.

- **Comfortable:** density factor 1.
- **Dense:** factor 0.82 for control heights, padding, and row rhythm. Text size and 24px-equivalent pointer target minimum do not shrink.
- Radius: 4 / 6 / 8 / 12 / 16 / 20 / full.
- Elevation: raised / overlay / modal. Dark mode uses surface tint and border before shadow.

## 5. Motion

| Role | Value | Use |
| --- | ---: | --- |
| Micro | 120ms | hover, press, toggle |
| Standard | 220ms | tabs, popovers, crossfade |
| Expressive | 340ms | dialogs, drawers, onboarding |
| Standard easing | `cubic-bezier(.2,0,0,1)` | most state changes |
| Emphasized | `cubic-bezier(.2,.8,.2,1)` | signature entrances |
| Enter / Exit | documented token pair | asymmetric overlays |

Animate transform/opacity; remove `will-change` after active motion. Sibling stagger ≤30ms and no more than three concurrent animated siblings. OS and in-app reduced-motion both collapse motion while retaining focus, announcements, and state changes. Full behavior is in [`animation-specs.md`](animation-specs.md).

## 6. Component contract

- **Button:** primary, secondary, ghost, destructive, danger-outline; sm/md/lg and icon sizes; loading keeps measured width and replaces content in place.
- **Input/textarea:** semantic surface and border; 2px focus + 2px offset; errors include message and icon.
- **Card:** flat/raised/interactive; no primitive colors.
- **Dialog:** Radix focus trap, Escape, focus return, labelled title/description, subtle scale/fade.
- **Menu/popover:** bounded height; window rows above 50 items.
- **Tabs:** arrow-key navigation, roving selection, selected state not color-only.
- **Skeleton:** geometry matches final content; static under reduced motion.
- **Tool card:** disclosure button with `aria-expanded`; status icon + text; arguments/results are isolated.
- **Approval:** `alertdialog`, initial focus on Allow once, Escape means Deny, no punitive animation.
- **Command palette:** combobox/listbox semantics, fuzzy search, complete keyboard operation, command categories.

## 7. Layout and direction

Shell order is title bar → activity rail → context sidebar → route workspace → status bar. Logical properties (`start`, `end`, `margin-inline`, `padding-inline`, `inset-inline`) are mandatory in component styling. Directional glyphs mirror; status and media glyphs do not.

Text from users and tools uses `dir="auto"`; code, URLs, model IDs, hashes, paths, latency, and shortcuts are `.ltr-island`. Locale/direction changes update root attributes synchronously without remounting.

## 8. State model

Every data surface implements:

1. Empty with explanation and one primary next action.
2. Skeleton after the 300ms threshold.
3. Partial data retained while refresh/retry occurs.
4. Inline recoverable error (never blanking safe cached data).
5. Offline/bridge-dead global banner with retry.
6. First-run path that works with echo and requires no account.

A route error boundary protects each workspace. Bridge calls are timeout-bounded; rendering never awaits bridge work.

## 9. Verification (P8)

```bash
cd apps/desktop
npm run tokens:check     # PASS — 12 themes, 208 tokens, 108 AA checks (recorded in P8-GATES.md)
npm run locales:generate
npm run typecheck        # attempted — node_modules unavailable (see GATES.md)
npm run lint             # attempted — node_modules unavailable (see GATES.md)
npm run format:check     # attempted — node_modules unavailable (see GATES.md)
npm test                 # attempted — vitest not installed (see GATES.md)
npm run build
npm run accessibility:check  # attempted — vitest not installed (see GATES.md)
```

- Logical properties verified (`grep -rE 'left:|right:|margin-left|margin-right|padding-left|padding-right' apps/desktop/src/components/ui/ apps/desktop/src/styles/ docs/design/tokens/` → zero hits).
- Focus ring theme-aware (`--ds-focus-ring`) in all 12 combos; visible under `:focus-visible`; `forced-colors: active` uses `Highlight`.
- WCAG 2.2 AA: target size ≥24 px, focus not obscured, redundant entry, contrast 1.4.3/1.4.11.
- Motion: only `transform`/`opacity`; reduced-motion collapses durations globally.
- RTL: logical borders/padding; Persian leading 1.72/1.75; `unicode-bidi: isolate`; no overflow at 320 px.
- Tests: primitives + a11y green where runnable; zero regressions in owned files.

Raw color literals are allowed only in `docs/design/tokens/`. Runtime components use semantic utilities. Any deliberate exception must be documented in the relevant stage handoff.
