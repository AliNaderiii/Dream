# Dream — Accessibility Audit (Gate G7) & RTL Verification (Gate G8)

Owner: UXR (a11y) + UID (RTL) · 2026-08-15 · Standard: **WCAG 2.1 AA**

## 1. Color contrast — measured (WCAG relative-luminance formula)

Computed programmatically from the shipped tokens (`tokens/dream.css`). AA thresholds: 4.5:1 normal text, 3:1 large text & UI components.

| Pair | Ratio | Verdict |
| --- | --- | --- |
| Light: `fg/primary` on `bg/surface` | 15.98 | AAA |
| Light: `fg/secondary` on `bg/surface` | 6.61 | AA |
| Light: `fg/muted` (#6E6E80, corrected) on `bg/canvas` | 4.71 | AA |
| Light: `accent/text` on `bg/surface` | 6.06 | AA |
| Light: success 700 on success 100 (badges) | 5.60 | AA |
| Light: warning 700 on warning 100 | 5.93 | AA |
| Light: danger 700 on danger 100 | 6.29 | AA |
| Light: info 700 on info 100 | 5.49 | AA |
| Light: `fg/inverse` on `accent/solid` (primary buttons) | 6.06 | AA |
| Light: focus ring on canvas | 4.24 | AA (UI ≥3:1) |
| Dark: `fg/primary` on `bg/surface` | 15.59 | AAA |
| Dark: `fg/secondary` on `bg/surface` | 7.28 | AAA |
| Dark: `fg/muted` on `bg/canvas` | 5.54 | AA |
| Dark: `accent/text` on `bg/surface` | 8.06 | AAA |
| Dark: success/warning/danger/info 400 on surface | 5.96–8.06 | AA–AAA |
| Dark: `fg/inverse` on `accent/solid` | 5.79 | AA |
| Dark: focus ring on canvas | 8.26 | AAA |

**Audit fix applied:** light `fg/muted` darkened `#77778A → #6E6E80`; light state badge text moved from the 600 to the 700 shades. Tokens JSON + CSS updated to match.

## 2. Color-vision deficiency (protanopia / deuteranopia)

- Risk tiers use **three redundant channels**: hue (green/amber/red), icon (`shield-check` / `shield-alert` / `shield-x`), and text label — legible in full grayscale.
- Success vs. danger never appear as color-only dots: tool-status dots are always accompanied by a text status label (`ok / error / blocked / running`).
- Charts default to the **Okabe–Ito** categorical palette; multi-series charts additionally require distinct patterns/dash styles (enforced in the chart builder spec).
- Data-grid issue cells: warning icon + tint + tooltip, never tint alone.
- Under deuteranopia simulation, the closest confusable pair (success 700 vs warning 700) still differs in lightness by ΔL* > 15 and always carries distinct icons.

## 3. Keyboard operation

- Every command reachable via **⌘K palette**; complete keymap in Settings → Shortcuts with rebinding.
- Composer: Enter send, Shift+Enter newline, Esc blur, `/` command autocomplete (arrow keys + Enter).
- Panes: `⌘\` split, `⌘1..4` focus, `⌥⌘←/→` resize (arrow semantics follow visual direction in RTL).
- Lists/grids: roving tabindex, Home/End, type-ahead; context-menu key opens row menus.
- Approval sheet: focus trapped, Enter = Allow once, Esc = Deny, Tab cycles the three actions; returns focus to composer on close.
- Focus visible always (2 px ring + 2 px offset); `:focus-visible` never suppressed. No keyboard traps; scrim click = safe dismiss (Deny).

## 4. Screen readers & semantics

- Streaming replies: `aria-live="polite"` on the active turn container; completion announced with model + duration.
- Approval sheet: `role="alertdialog"`, `aria-modal`, labelled by title.
- Tool-call cards: `aria-expanded` on headers; status conveyed in text.
- Subagent status changes announced via a polite live region; badge counts have accessible labels ("2 subagents running").
- Landmarks: rail = `nav`, sidebar = `aside/complementary`, workspace = `main`, status bar = `contentinfo`.
- Persian: `lang="fa"` at root in FA locale; LTR islands additionally get `lang="en"` where content is English/code so pronunciation switches correctly.

## 5. Touch & zoom

- Desktop hit targets ≥ 24×24 px; mobile gateway ≥ 44×44 px (tab bar, approval buttons).
- Layout reflows without horizontal scroll at 400% zoom / 320 px width (single-pane mobile rules apply).
- No information conveyed by hover alone: all hover reveals (message actions) have menu/keyboard equivalents.

## 6. Motion & vestibular safety

- `prefers-reduced-motion` collapses all durations to 0 (token-level media query) — see `animation-specs.md` per-item column; app-level "Reduce motion" setting can force it regardless of OS.
- No parallax, no auto-playing motion; blink limited to the 1 Hz caret which is disabled under reduced motion.

## 7. RTL verification (Gate G8)

Checklist executed against the prototype (`prototype/` with فارسی · RTL toggle):

- [x] Root `dir="rtl"`: activity rail, sidebar, status bar, composer, sheets all mirror via logical properties (no `left/right` in stylesheet — verified: prototype.css uses inline-start/end throughout).
- [x] Directional icons (send arrow, chevrons) mirror via `scaleX(-1)` on `.dir`; shields/status dots do not mirror.
- [x] Switch knob travels start→end (translated −16 px in RTL).
- [x] LTR islands: tool names/args, JSON, logs, URLs, file paths, latency/token figures rendered with `direction:ltr; unicode-bidi:isolate` — Persian sentence punctuation lands on the correct side (the M23 `desktop.py` defect is fixed structurally, not with RLM hacks).
- [x] Mixed-script rows (Persian skill names in lists, English tool names in Persian cards) isolate each segment (`unicode-bidi: isolate` on `.t`, `.txt`, `.lbl`) — no scrambling, ellipsis truncation stays on the inline-end.
- [x] Onboarding step slide mirrors (separate RTL keyframes).
- [x] Numerals: FA strings use Persian digits (۰-۹); grid/latency values remain Latin + LTR by design.
- [x] Dual calendar: Jalali primary / Gregorian secondary in FA (e.g. ۱۴۰۴/۰۵/۲۴ — 2026-08-15).
- [x] Text overflow: long Persian rows ellipsize logically; no horizontal-scrollbar workaround (the M26 defect class).

## 8. Open items for implementation phase (P-01+)

1. Automated contrast regression test wired to the token files (script from this audit can be committed as a CI check).
2. Screen-reader pass on real Tauri build (WebView differences vs. browser).
3. Persian screen-reader verification (NVDA + Vazirmatn rendering).
4. Windows High Contrast / forced-colors mode audit.

**Gate G7: PASSED** (with the two token corrections applied) · **Gate G8: PASSED**
