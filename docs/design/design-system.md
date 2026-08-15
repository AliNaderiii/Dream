# Dream Design System — "Rooya" (رؤیا)

Version 1.0 · Phase 0 / Gate G4 · Owner: UID, documented by DPM
Target stack: **Tauri 2 + React + Tailwind CSS v4 + Shadcn/ui + Lucide icons**

Machine-readable tokens: [`tokens/dream.tokens.json`](tokens/dream.tokens.json) (Tokens Studio / W3C format, importable into Figma) and [`tokens/dream.css`](tokens/dream.css) (CSS custom properties, drop-in for Tailwind `@theme`).

---

## 1. Principles

1. **Honest surfaces.** The UI never hides what the agent does: tools, network, risk, and provenance are visible primitives, not debug modes.
2. **Two scripts, one rhythm.** Latin (Inter) and Persian (Vazirmatn) are co-primary. Every component is designed in both directions; direction is a layout property (`dir`), never a text hack.
3. **Calm by default, dense on demand.** Comfortable density is default; compact density is a token switch, not a redesign.
4. **Risk is never color-only.** `safe / guarded / dangerous` always pair color with icon + label (protanopia/deuteranopia-safe).
5. **Motion explains, never decorates.** 120–320 ms, transform/opacity only, honors `prefers-reduced-motion`.

---

## 2. Color

### 2.1 Primitive scales

Neutral is a cool slate tuned so dark mode isn't pure black (reduces smearing on OLED, keeps elevation readable).

| Step | `neutral` | `primary` (Dream violet) | `success` | `warning` | `danger` | `info` |
| --- | --- | --- | --- | --- | --- | --- |
| 50  | `#F8F8FA` | `#F1EFFE` | `#EFFAF3` | `#FFF7EB` | `#FEF1F1` | `#EFF6FF` |
| 100 | `#F1F1F4` | `#E4E0FD` | `#D8F3E2` | `#FDEBCF` | `#FDE3E3` | `#DBEAFE` |
| 200 | `#E4E4E9` | `#CCC5FB` | `#B2E5C6` | `#FAD79F` | `#F9C6C6` | `#BFDBFE` |
| 300 | `#CFCFD8` | `#ADA1F7` | `#7FD3A2` | `#F5BC63` | `#F39B9B` | `#93C5FD` |
| 400 | `#A2A2B0` | `#8F82F0` | `#4BBA7D` | `#E89B2C` | `#EA6B6B` | `#60A5FA` |
| 500 | `#77778A` | `#7263E8` | `#2E9E63` | `#C97E12` | `#DC4444` | `#3B82F6` |
| 600 | `#5B5B70` | `#5D4DD3` | `#22824F` | `#A36305` | `#C22B2B` | `#2563EB` |
| 700 | `#474759` | `#4C3EB2` | `#1C6A41` | `#814E08` | `#A02222` | `#1D4ED8` |
| 800 | `#333342` | `#3D3390` | `#175534` | `#653E0C` | `#821E1E` | `#1E40AF` |
| 900 | `#212129` | `#2F2870` | `#123F27` | `#4B2F0C` | `#621919` | `#1E3A8A` |
| 950 | `#141419` | `#1D1946` | `#0A2818` | `#301F08` | `#421111` | `#172554` |

Categorical palette for charts (colorblind-safe, based on Okabe–Ito):
`#0072B2 #E69F00 #009E73 #CC79A7 #56B4E9 #D55E00 #F0E442 #999999` — plus shape/line-style differentiation is mandatory in multi-series charts.

### 2.2 Semantic tokens (aliases)

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `bg/canvas` | `neutral.50` | `#111116` | window background |
| `bg/surface` | `#FFFFFF` | `neutral.950` | cards, panes |
| `bg/surface-2` | `neutral.100` | `#1B1B22` | nested surfaces, code blocks |
| `bg/sunken` | `neutral.200` | `#0C0C10` | wells, input troughs |
| `bg/overlay` | `#FFFFFF` | `#20202A` | modals, popovers (± shadow) |
| `fg/primary` | `neutral.900` | `#ECECF1` | body text (≥ 7:1) |
| `fg/secondary` | `neutral.600` | `neutral.400` | labels, meta (≥ 4.5:1) |
| `fg/muted` | `#6E6E80` | `#8A8A9A` | placeholders, ≥ 4.5:1 on canvas (light value darkened from neutral.500 after contrast audit) |
| `fg/inverse` | `#FFFFFF` | `#141419` | text on solid accents |
| `accent/solid` | `primary.600` | `primary.400` | primary buttons, active states |
| `accent/text` | `primary.600` | `primary.300` | links, active labels |
| `accent/soft` | `primary.100` | `primary.900` @40% | selected rows, active nav |
| `border/default` | `neutral.200` | `#2A2A35` | hairlines |
| `border/strong` | `neutral.300` | `#3A3A48` | inputs, focused pane edge |
| `focus/ring` | `primary.500` | `primary.300` | 2px ring + 2px offset, always visible |
| `state/success-*` | `700 / soft 100` | `400 / 900@40%` | + `check-circle` icon (700 chosen for ≥4.5:1 on the 100 tint) |
| `state/warning-*` | `700 / soft 100` | `400 / 900@40%` | + `alert-triangle` icon |
| `state/danger-*` | `700 / soft 100` | `400 / 900@40%` | + `octagon-alert` icon |
| `state/info-*` | `700 / soft 100` | `400 / 900@40%` | + `info` icon |

### 2.3 Risk-tier trio (house-specific)

| Tier | Color | Icon (Lucide) | Label | Shape cue |
| --- | --- | --- | --- | --- |
| `safe` | `success` | `shield-check` | Safe · ایمن | circle badge |
| `guarded` | `warning` | `shield-alert` | Guarded · محافظت‌شده | rounded-square badge |
| `dangerous` | `danger` | `shield-x` | Dangerous · خطرناک | octagon badge |

Three redundant channels (hue, icon, silhouette) → distinguishable under protanopia/deuteranopia and in grayscale.

---

## 3. Typography

| Role | Latin | Persian/Arabic | Notes |
| --- | --- | --- | --- |
| UI & body | **Inter** (variable) | **Vazirmatn** (variable) | x-heights match within ~2%; set `font-family: Inter, Vazirmatn, system-ui` (LTR) and `Vazirmatn, Inter, system-ui` (RTL) |
| Mono / code / data | **JetBrains Mono** | (digits/code stay LTR) | `font-variant-numeric: tabular-nums` in grids |
| Licenses | OFL | OFL | open-source friendly ✅ |

Scale (rem, 1rem = 16px; Persian body gets `+0.125 line-height` because Vazirmatn's vertical metrics are taller):

| Token | Size / line | Weight | Use |
| --- | --- | --- | --- |
| `display` | 30/38 | 700 | onboarding hero |
| `h1` | 24/32 | 650 | page titles |
| `h2` | 20/28 | 650 | pane headers |
| `h3` | 16/24 | 600 | card titles |
| `body` | 14/22 (FA 14/24) | 400/500 | default UI |
| `body-lg` | 16/26 (FA 16/28) | 400 | transcript text |
| `caption` | 12/18 | 500 | meta, timestamps |
| `micro` | 11/16 | 600 caps | badges, overlines (never for Persian caps — use 600 normal) |
| `code` | 13/20 | 450 | mono blocks |

Numerals: setting `General → Numerals` renders Persian digits (۰۱۲۳) via `font-feature-settings`/locale formatting in FA locale; data grids always offer a Latin-digit override for spreadsheet parity.

---

## 4. Spacing, radius, elevation

- **Spacing** (4px base): `0.5→2, 1→4, 1.5→6, 2→8, 3→12, 4→16, 5→20, 6→24, 8→32, 10→40, 12→48, 16→64`. Density switch: compact multiplies component paddings by 0.75 (token-level, `density-scale`).
- **Radius**: `xs 4 · sm 6 · md 8 · lg 12 · xl 16 · full 9999`. Buttons/inputs `md`; cards/panes `lg`; modals `xl`; chips/badges `full`.
- **Elevation** (light / dark — dark relies more on surface tint than shadow):

| Token | Light shadow | Dark treatment |
| --- | --- | --- |
| `e0` flat | none | surface color only |
| `e1` raised | `0 1px 2px rgb(20 20 25 / .06), 0 1px 3px rgb(20 20 25 / .10)` | surface-2 + 1px `border/default` |
| `e2` overlay | `0 4px 12px rgb(20 20 25 / .10), 0 2px 4px / .08` | overlay bg + border + `0 4px 16px rgb(0 0 0 / .45)` |
| `e3` modal | `0 12px 32px rgb(20 20 25 / .16), 0 4px 8px / .08` | + `0 12px 40px rgb(0 0 0 / .6)` |

---

## 5. Motion

| Token | Value | Use |
| --- | --- | --- |
| `duration/fast` | 120 ms | hover, toggle knobs |
| `duration/base` | 180 ms | fades, popovers, tab switch |
| `duration/slow` | 260 ms | modals, drawers, pane collapse |
| `duration/slower` | 320 ms | onboarding step slide |
| `ease/standard` | `cubic-bezier(.2,.0,.0,1)` | most transitions |
| `ease/enter` | `cubic-bezier(.05,.7,.1,1)` | elements appearing |
| `ease/exit` | `cubic-bezier(.3,0,.8,.15)` | elements leaving |

Rules: animate `transform`/`opacity` only; no layout-property animation except pane resize (which is direct manipulation, not animation). `prefers-reduced-motion`: all non-essential motion → 0 ms; streaming caret becomes steady; skeleton shimmer becomes static. Full specs in [`animation-specs.md`](animation-specs.md).

---

## 6. Iconography

**Lucide** (ISC license). 16px in dense chrome, 20px default, 24px in empty states. Stroke 1.75. Directional icons (`arrow-*`, `chevron-*`, `corner-*`, `log-in/out`, `list-ordered`) **mirror in RTL**; non-directional and media/progress icons do not. House icons (added as custom Lucide-style glyphs): `memory-kind-semantic` (book), `memory-kind-episodic` (clock-calendar), `memory-kind-procedural` (list-checks), `subagent` (bot with orbit), `provenance` (git-branch-tree), `jalali-calendar`.

---

## 7. Layout system

- App shell: **activity rail** (48px icons: Chat, Projects, Memory, Skills, Subagents, Data, Provenance, Settings) → **context sidebar** (260px, collapsible, e.g. session list) → **workspace** (1–4 panes) → **status bar** (24px: provider + local/online dot, network switch, running subagents, sync).
- Pane manager: VS Code-style split model. Min pane width 320px; drag handle 6px hit area (visible 1px, thickens to 3px + accent on hover); double-click handle = equalize; `⌘\` split, `⌘⇧\` split down, `⌘1..4` focus pane. Panes can host: conversation, data grid, chart, report, file browser, provenance, subagent log.
- Breakpoints (web gateway): `sm 640 · md 768 · lg 1024 · xl 1280`. Below `md`: single pane + bottom tab bar (Chat, Sessions, Approvals, Settings); sidebar becomes a sheet.
- RTL: the entire shell mirrors (rail on right, sidebar right-of-rail, status bar order flipped). Only LTR islands: code, URLs, keys, latency numbers, file paths.

---

## 8. Core component specs (Shadcn/ui mapping)

| Component | Shadcn base | Dream-specific spec |
| --- | --- | --- |
| Button | `button` | variants: primary (accent/solid), secondary (surface+border), ghost, destructive, danger-outline; sizes sm 28 / md 32 / lg 40; loading state swaps label→spinner keeping width |
| Input / Textarea | `input`, `textarea` | 32/40px; focus = `border/strong` + focus ring; error state adds icon + caption, never border-color alone |
| Select / Combobox | `select`, `command` | provider & model pickers get monogram avatars + latency chip |
| Checkbox / Radio / Switch | same | switch knob animates 120 ms; RTL: knob travels left |
| Slider | `slider` | importance slider shows value bubble while dragging |
| Tabs | `tabs` | underline style in panes, pill style in settings |
| Badge / Chip | `badge` | risk badges per §2.3; memory-kind chips (icon + label); removable chips get 24px hit target on ✕ |
| Tooltip | `tooltip` | 600 ms delay, 0 ms when moving between targets |
| Modal / Drawer / Sheet | `dialog`, `sheet` | approval dialog is a **sheet anchored above composer**, not a centered modal — keeps transcript visible |
| Dropdown / Context menu | `dropdown-menu` | every list row has a context menu; all items keyboard-reachable |
| Toast | `sonner` | bottom inline-end; destructive-action toasts always carry Undo (10 s) |
| Progress / Spinner / Skeleton | `progress`, `skeleton` | skeleton over spinner for loads > 300 ms; spinner only inside buttons |
| Breadcrumbs / Pagination | `breadcrumb`, `pagination` | breadcrumbs in file browser and provenance path |
| **Tool-call card** | composite | header: status dot (queued/running/ok/error/blocked) + tool name + server badge (MCP) + risk badge; body (expandable): args JSON, result JSON/stderr; monospace, LTR island |
| **Context chip** | composite | "Used N memories · M reminders" — expands to scored memory list with kind chips |
| **Approval sheet** | composite | title = plain-language action; args table; risk badge trio; buttons: Deny (secondary) / Allow once (primary) / Always allow (ghost + shield, opens scope note); ⏎ = Allow once, Esc = Deny; full spec in animation-specs.md §4 |
| **Turn footer** | composite | model · duration · tokens · provenance link, `caption` style |
| **Data grid** | composite (TanStack Table) | virtualized; type icons per column; issue cells: icon + tinted bg + tooltip; tabular-nums |
| **Step list** | composite | ordered, revert per step, "view code" per step; running step gets progress caret |
| **Empty state** | composite | 24px icon, one-line explanation, primary action, optional docs link — every screen ships one |

Full anatomy drawings for composites are in the prototype (`prototype/`), which is the visual source of truth.

---

## 9. States matrix (mandatory per screen)

Every screen must design: **empty · loading (skeleton) · partial/streaming · error · offline**. The prototype's "State" switcher demonstrates these for core screens. A screen PR that lacks any of the five states fails review (Gate G7 rule).

---

## 10. Accessibility contract (summary — full audit in `accessibility-audit.md`)

- Text contrast ≥ 4.5:1 (body), ≥ 3:1 (large/UI); verified for both themes in the audit.
- Focus visible always: 2px ring, 2px offset, never removed.
- Full keyboard map; roving tabindex in lists/grids; `⌘K` palette reaches every command.
- Live regions: streaming replies `aria-live="polite"`; approval sheet `role="alertdialog"`; subagent status changes announced.
- Hit targets ≥ 24×24 CSS px (AA), 44×44 on touch/mobile gateway.
- Risk & validity never color-only (see §2.3, §8 Input).

---

**Gate G4: PASSED** — tokens defined and exported, components specified with Shadcn mapping, dual-script typography set, both themes covered.
