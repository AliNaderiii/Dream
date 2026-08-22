# Dream motion and interaction specification — Rooya 2

**Version 2.0 · 2026-08-22 · Owner: FLUX**

Motion explains causality and activity. It never delays input, hides network state, or turns background work into spectacle.

## Tokens

| Role | Duration | Easing | Typical use |
| --- | ---: | --- | --- |
| Micro | 120ms (allowed range 100–150) | standard | hover, press, switch |
| Standard | 220ms (allowed range 200–250) | standard / enter | menu, tab, crossfade |
| Expressive | 340ms (allowed range 300–400) | emphasized / enter | dialog, onboarding |

- Standard: `cubic-bezier(0.2, 0, 0, 1)`
- Emphasized: `cubic-bezier(0.2, 0.8, 0.2, 1)`
- Enter: `cubic-bezier(0.05, 0.7, 0.1, 1)`
- Exit: `cubic-bezier(0.3, 0, 0.8, 0.15)`

Sibling stagger is at most **30ms**. At most **three** siblings animate concurrently. Longer lists do not cascade; they settle as one region.

## Performance contract

- Animate compositor-friendly `transform` and `opacity`. Color transitions are allowed for direct interaction feedback.
- Never animate width, height, top, left, margin, padding, or grid sizing.
- A pane resize is direct pointer manipulation with no transition.
- `will-change` may exist only during active WAAPI/FLIP work and must be removed on finish/cancel.
- Reordering uses FLIP: read initial rectangles once, commit order, read final rectangles once, invert with transform, play to identity.
- Streaming token writes are coalesced to one store update per animation frame. No token path reads `scrollWidth`, `scrollHeight`, or a bounding box.
- Scroll geometry is read only in the user's scroll handler to update “follow tail.” Programmatic tail following schedules one write in `requestAnimationFrame`.

## Streaming signature

1. New tokens append through `createFrameBatcher`; any number of chunks in one frame becomes one React/store update.
2. The active assistant row has a low-contrast sweep-light rendered by a translated pseudo-element. It creates no layout or paint-dependent JS loop.
3. The transcript follows the active thought while the reader remains within the tail threshold.
4. If the user scrolls up, following stops immediately. New tokens never pull them away. Returning to the bottom resumes following.
5. Completion removes sweep and caret, then announces completion through the existing polite live region.
6. Transcript rows below the fold use `content-visibility: auto` with an intrinsic block-size estimate.

Reduced motion: no sweep or pulsing caret; token batching and scroll ownership behavior are unchanged.

## Tool-call cards

- A running card uses the same translated sweep and a static status glyph, not a spinner.
- The disclosure header is always operable and exposes `aria-expanded` / `aria-controls`.
- Detail appears with opacity + a 6px-equivalent transform; the card does not tween height.
- Completion swaps status icon/text and removes activity motion in the same render. Success is calm—no bounce or confetti.
- Errors and blocks retain arguments and recovery context.

Reduced motion: details appear instantly and status changes remain textual.

## Approval alert dialog

1. Overlay and surface enter together. Surface uses opacity + scale 0.985→1 + a short block-axis translation at Expressive maximum.
2. Focus is trapped by Radix and begins on **Allow once**. Escape and outside dismissal both resolve to **Deny** (fail closed).
3. Arguments remain selectable and LTR-isolated; risk remains visible.
4. Deny uses the same calm close as approval—never shake, flash, or punish.
5. Focus returns to the invoking workflow.

Reduced motion: dialog appears instantly; focus and fail-closed behavior do not change.

## Shell and navigation

- Rail hover/selection: Micro color transition. Active marker does not slide between remote routes.
- Route switch: 120ms opacity only; lazy-route skeleton retains geometry.
- Sidebar collapse: layout commits immediately, workspace content may crossfade Standard.
- Status bar background activity: a thin traveling light. A spinner is reserved for in-button work only.
- Popovers/tooltips: 4–6px-equivalent transform + fade, Standard/Micro.
- Command palette: must become interactive in <100ms. Search is synchronous over the local registry; no network or bridge work occurs on open.

## Skeletons and progress

A wait predicted over 300ms uses geometry-matched skeletons. The shimmer is a translated pseudo-element and never animates background position. Reduced motion renders a static two-tone shape. Determinate work uses progress; indeterminate work communicates stage text and cancellation where supported.

## Reduced-motion implementation

Two equivalent inputs collapse duration tokens:

```css
@media (prefers-reduced-motion: reduce) { /* OS */ }
[data-reduce-motion='true'] { /* in-app override */ }
```

Both remove repeated animation and smooth scrolling. Tests verify root state and static fallback. Essential state, focus, live announcements, and progress remain.
