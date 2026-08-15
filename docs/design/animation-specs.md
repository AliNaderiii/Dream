# Dream — Interaction & Motion Specs (Gate G6 support)

Owner: IMD · v1.0 · All values reference motion tokens in `design-system.md` §5.
Global rules: **transform/opacity only**, 60 fps budget, `prefers-reduced-motion: reduce` zeroes all non-essential motion (spec per item below). Everything here is demonstrated live in `prototype/`.

## 1. Buttons & controls
| Interaction | Spec | Reduced motion |
| --- | --- | --- |
| Button hover | background/filter change, `fast` (120 ms) `standard` | instant |
| Button press | `scale(0.92)` on send icon, `fast` | instant |
| Button loading | label crossfades to spinner, width locked (no reflow), `base` | swap without fade |
| Switch toggle | knob `translateX(16px)` (mirrored in RTL), `fast` | instant |
| Focus ring | appears instantly — never animated (a11y) | same |

## 2. Streaming response
- Tokens append as text; **no per-character animation** (jank risk on long replies). The transcript container autoscrolls only while user is at bottom; any manual scroll pauses follow.
- Caret: 7×16 px block in `accent/solid`, `blink 1s step-end infinite`. Reduced motion → steady caret.
- Tool-status dot `running`: opacity pulse 1.2 s ease-in-out. Reduced motion → static dot + "running" label (label always present anyway).
- Turn entry: `translateY(6px) + fade`, `base` (180 ms) `enter`. Reduced motion → none.

## 3. Panes
- **Drag resize is direct manipulation — zero animation, zero transition** on width/height (transitions on layout would fight the pointer). Live width tooltip.
- Handle hover: visible line 1px → 3px accent, `fast`.
- Pane open/close (split, collapse): the *entering* pane fades/slides 8 px, `slow` (260 ms) `enter`; layout change itself is instant. Reduced motion → instant.
- Double-click handle → equalize: instant (data change), contents fade `base`.

## 4. Approval sheet (signature moment)
1. Scrim fades to 20% black, `slow` `standard` — transcript stays readable (never full blackout).
2. Sheet: `translateY(16px)→0 + opacity 0→1`, `slow` (260 ms) `enter`, anchored above composer.
3. Focus moves to **Allow once**; Esc = Deny; focus trapped; `role="alertdialog"`.
4. On decision: sheet exits down `base` `exit`; a toast confirms the outcome (with the model-refusal note on Deny).
5. Deny must **never** feel punitive: no shake, no red flash; calm exit + informative toast.
Reduced motion: scrim/sheet appear instantly; focus behavior unchanged.

## 5. Overlays, navigation, lists
| Element | Enter | Exit |
| --- | --- | --- |
| Modal (`e3`) | scale 0.98→1 + fade, `slow` `enter` | fade, `base` `exit` |
| Popover/menu (`e2`) | fade + 4 px slide from anchor side (logical: `inset-inline-start` aware), `base` | fade `fast` |
| Toast | rise 6 px + fade `base` `enter`, auto-dismiss 5 s (10 s when it carries Undo) | fade `base` |
| Tab switch | underline slides `base` `standard`; panels crossfade `fast` | instant |
| View switch (rail) | new view fades 120 ms; **no slide** (keeps spatial model calm) | — |
| Onboarding step | slide 24 px `slower` (320 ms), direction-aware (mirrors in RTL) | reduced: crossfade |
| List row hover | background `fast` | — |
| Row delete | collapse height via `grid-template-rows` trick + fade `base`; Undo toast | instant removal |

## 6. Loading / skeleton
- Any wait > 300 ms shows skeleton (shimmer: background-position sweep 1.4 s linear). Reduced motion → static two-tone skeleton.
- Spinners only inside buttons and tiny inline contexts.
- Chart bars grow from baseline `slow` `standard` on first render only; data updates transition height `slow`. Reduced motion → instant.

## 7. Performance contract
- Only `transform`, `opacity`, `background-color`, `filter` may transition. Never `width/height/top/left` (exception: pane drag = no transition at all).
- `will-change` applied only during an active animation; removed after.
- Streaming render batched via `requestAnimationFrame`; DOM appends coalesced (the prototype simulates 60 ms word batches).
- Virtualized lists (sessions, memories, grid rows) — no entry animation on virtual scroll, only on true insertion.
