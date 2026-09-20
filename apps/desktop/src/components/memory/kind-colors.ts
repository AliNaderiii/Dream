/**
 * Memory-kind colour mapping.
 *
 * Kept in a module without components so React Fast Refresh stays intact for
 * `kind-badge.tsx` (react-refresh/only-export-components). Colours use the
 * Okabe–Ito categorical ramp from `theme.css` — semantic = chart-1 blue,
 * episodic = chart-3 green, procedural = p-500 purple. Colour is never the
 * only signal: the kind name is always spelled out (design-system §2.3).
 */

/** Per-kind swatch, keyed by the backend's kind string. */
export const KIND_COLOR: Record<string, string> = {
  semantic: 'var(--color-chart-1)',
  episodic: 'var(--color-chart-3)',
  procedural: 'var(--color-p-500)',
};
