# Dream visual language — calm intelligence

**Version 2.1 · 2026-08-22 · Owner: LUMEN / Product Design Systems**

Dream should feel **calm, precise, and trustworthy** before it feels “AI.” Its craft comes from rhythm, legibility, and honest state communication—not spectacle. This document describes the implemented Tauri desktop language; the token source of truth is [`tokens/dream.tokens.json`](./tokens/dream.tokens.json).

## Emotional direction

- **Calm:** quiet neutral surfaces, one accent family at a time, deliberate negative space, and no attention competition between background work and the user’s current task.
- **Precise:** tabular metrics, visible provenance, aligned baselines, bounded lists, and controls whose labels describe the exact operation.
- **Trustworthy:** network locality, risk, approval, partial results, and errors remain visible. “Offline” is a supported recoverable state, never a shame state.
- **Persian-native:** فارسی is not a mirrored afterthought. Vazirmatn, taller leading, mixed-direction isolation, Jalali context, and Persian numeral display belong to the core language.

## Three-theme rationale

The themes answer different working conditions without changing component meaning or information hierarchy.

- **Light** is cool and analytical, optimized for long research and data sessions in bright environments. Muted text is deliberately darker than a fashionable low-contrast gray; it measures 5.47:1 on the canvas in every accent.
- **Warm** is paper-like and comfortable for reading-heavy work. It is an explicit choice, not a system-theme alias and not a nostalgic sepia filter.
- **Dark** is blue-black rather than pure black. Tint and border separation preserve depth without halation or a neon-on-black “AI console” look.

Violet is the signature default. Ocean, Forest, and Ember are equivalent accent sets, not bespoke component skins. Accent changes never redefine success, warning, danger, or information semantics.

## Visual grammar

### Surfaces and color

Three to four surface steps create subtle depth: canvas → base → raised → overlay. Light and Warm use low-opacity shadows; Dark primarily uses tint and border separation. Overlays may dim the workspace but keep enough context to support an informed approval decision.

The semantic contract is `surface`, `text`, `border`, `accent`, and `status`. Components consume semantic tokens rather than raw palette values. Risk always combines a label, icon, and color. Restrained gradients are allowed only as low-contrast ambient fields or traveling activity light; they never carry meaning.

### Typography and bidirectionality

Inter Variable and Vazirmatn Variable are co-primary. Their perceived body size is matched at the base scale. Persian body leading is **1.72** minimum; long-form Persian content uses **1.75**. Headings are compact but never tightly tracked. Uppercase microcopy is Latin-only.

Mixed-direction content uses `unicode-bidi: isolate`. Code, URLs, hashes, paths, model identifiers, and normalized data are LTR islands. The Persian numeral option changes only the display layer; bridge values and persisted data remain normalized. Layout uses logical inline/block properties so the same component structure mirrors under `dir="rtl"`.

### Shape, depth, and iconography

A restrained radius ladder communicates hierarchy: compact controls, cards, and overlays become progressively softer, but a control does not become “premium” by accumulating nested borders and shadows.

Lucide is the only icon source. Directional icons mirror in RTL; media, status, brand, and clock symbols do not. Icons support labels rather than replace unfamiliar actions. Custom illustration, when justified, is inline SVG using `currentColor`.

## Motion philosophy

Motion explains cause, location, or continuity. It does not decorate waiting.

- Micro feedback uses the fast token; ordinary transitions use the standard token; expressive timing is reserved for overlays and first-run transitions.
- Transform and opacity are the animation workhorses. Layout properties do not animate during streaming.
- At most three sibling elements animate concurrently, and sibling stagger is at most 30ms.
- Streaming writes are coalesced to one store update per animation frame. Sticky-tail ownership stops when the reader scrolls away from the end.
- Skeletons communicate structure; determinate progress communicates measurable work; a static state plus recovery action is preferred to an endless spinner.
- `prefers-reduced-motion: reduce` and the persistent in-app Reduce motion setting are complete alternate behaviors: repeated animations stop, transitions become effectively immediate, and scroll behavior is automatic. Streaming, palette, dialogs, pane resize, toast, and tooltip coverage is executable in `src/styles/reduced-motion.test.ts`.

## Product signatures

1. **Streaming sweep:** a soft traveling light marks the active answer and becomes static under reduced motion.
2. **Tool transparency:** tool cards expose status, arguments, results, and approvals in the transcript.
3. **Calm approval:** a focused alert dialog explains risk and scope and treats Deny as a normal safe decision.
4. **Living status line:** background work uses bounded, truthful state instead of a theatrical indefinite loop.
5. **Why this memory:** retrieval score factors and weights are visual and inspectable.
6. **Operational continuity:** empty, loading, actionable error, offline, and recovered states share the same stable layout.

## Deliberate restraint — what Dream does not do

- No neon-on-black “AI” aesthetic, glassmorphism stack, blur-heavy chrome, or decorative gradient behind body copy.
- No low-contrast muted text. Normal semantic text targets at least 4.5:1; Light muted text targets at least 5.0:1.
- No color-only state, mystery icon, hidden network call, fabricated progress, or success message before the bridge settles.
- No endless spinner where a skeleton, determinate progress, partial result, timeout, or recovery action is available.
- No physical left/right styling for logical UI edges and no mutation of normalized data to make RTL look correct.
- No animation framework for effects that CSS tokens and transform/opacity can express.
- No unbounded transcript, session, scheduler-history, or log DOM after 100 rows.
- No telemetry or analytics in the interaction layer.

## Design-system verification (P8)

- Logical properties only (`padding-inline`, `margin-inline`, `start/end`, `border-inline-start/end`) — no physical `left/right` in owned CSS.
- Theme-aware focus ring (`--ds-focus-ring`) visible in all 12 theme/accent combos; never suppressed.
- Pointer targets ≥ 24 px; dense mode retains 24 px minimum.
- RTL tables usable at 320 px width; `unicode-bidi: isolate` for mixed content.
- WCAG 2.2 AA documented (contrast, target size, focus not obscured, redundant entry).
- Motion only `transform`/`opacity`; fully disabled under `prefers-reduced-motion` and `[data-reduce-motion='true']`.

## Review questions

A new UI proposal should answer yes to all of these:

1. Is state and locality honest even when work fails or goes offline?
2. Does it use semantic tokens and remain legible in Light, Warm, and Dark?
3. Does it work in LTR and RTL without a second component implementation?
4. Is motion explanatory, bounded, and dispensable under reduced motion?
5. Does keyboard and assistive-technology behavior remain equivalent to pointer behavior?
6. Does the proposal remove complexity rather than merely restyle it?
