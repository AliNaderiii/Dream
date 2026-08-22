# Dream visual language — calm intelligence

**Version 2.0 · 2026-08-22 · Owner: LUMEN / Product Design Systems**

Dream should feel **calm, precise, and trustworthy** before it feels “AI.” Its craft comes from rhythm, legibility, and honest state communication—not spectacle.

## Emotional direction

- **Calm:** quiet neutral surfaces, one accent family at a time, deliberate negative space.
- **Precise:** tabular metrics, visible provenance, aligned baselines, unambiguous controls.
- **Trustworthy:** network locality, risk, approval, partial results, and errors remain visible. “Offline” is a supported state, never a shame state.
- **Persian-native:** فارسی is not a mirrored afterthought. Vazirmatn, taller leading, mixed-direction isolation, Jalali context, and Persian numeral display all belong to the core language.

## Visual grammar

### Surfaces

Three to four surface steps create subtle depth: canvas → base → raised → overlay. Light and Warm use low-opacity shadows; Dark primarily uses tint and border separation. There is no translucent glass stack, glowing neon, or blur-heavy chrome. Overlays may dim the workspace, but keep enough context to support an informed approval decision.

### Color

The semantic contract is `surface`, `text`, `border`, `accent`, and `status`. Components never consume palette primitives directly. Violet is the signature default; Ocean, Forest, and Ember are equivalent accent sets—not bespoke component skins.

- **Light:** cool and analytical, optimized for long research sessions.
- **Warm:** paper-like and comfortable, without sepia nostalgia or reduced contrast.
- **Dark:** blue-black rather than pure black, preserving depth on modest displays.
- Restrained gradients are allowed only as low-contrast ambient fields or traveling activity light. They never carry meaning.
- Risk always combines label, icon, and color.

### Typography

Inter Variable and Vazirmatn Variable are co-primary. Their perceived body size is matched at 14px-equivalent. Persian body leading is **1.72** minimum; long-form Persian content uses **1.75**. Headings are compact but never tightly tracked. Uppercase microcopy is Latin-only.

Mixed-direction content uses `unicode-bidi: isolate`. Code, URLs, hashes, paths, model identifiers, and Latin digits in data are LTR islands. The Persian numeral option changes the display layer only; bridge values and persisted data stay normalized.

### Shape and depth

A restrained radius ladder (4/6/8/12/16/20) communicates hierarchy. Inputs and buttons use 8; cards 12; overlays 16–20; badges are fully rounded. A control does not become “premium” by accumulating nested borders and shadows.

### Iconography

Lucide is the only icon source. Default stroke is 1.75 at 16–20px-equivalent. Directional icons mirror in RTL; media, status, brands, and clocks do not. Icons support labels rather than replace unfamiliar actions.

## Interaction grammar

- Micro feedback: 100–150ms.
- Standard transitions: 200–250ms.
- Expressive moments: 300–400ms, used sparingly for overlays and first-run transitions.
- At most three sibling elements animate concurrently; stagger is at most 30ms.
- Transform and opacity are the animation workhorses. Streaming reads and writes are coalesced per animation frame.
- Reduced motion is a complete alternate behavior, not merely shorter durations.

## Product signatures

1. **Streaming sweep:** a soft traveling light marks the active answer; it stops competing for attention once complete.
2. **Tool transparency:** tool cards expose status, arguments, results, and approvals in the transcript.
3. **Calm approval:** a focused alert dialog enters subtly, explains risk and scope, and treats Deny as a normal safe decision.
4. **Living status line:** background work uses a traveling light—not an indefinite spinner.
5. **Why this memory:** retrieval score factors are visual and inspectable.

## Anti-patterns

- No neon-on-black “AI” aesthetic.
- No glassmorphism stacks or low-contrast frosted text.
- No decorative gradients behind body copy.
- No endless spinner where progress, skeleton, partial data, or recovery is available.
- No color-only status, mystery icon, surprise network call, or layout motion during streaming.
- No physical left/right styling for logical UI edges.
