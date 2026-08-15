/** Platform and environment detection helpers. */

/**
 * True when running inside the Tauri WebView.
 *
 * The shell also runs in a plain browser during `npm run dev` and in unit tests,
 * where every native call must be skipped rather than throwing.
 */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/** True when the user agent reports macOS (used for ⌘ vs Ctrl and traffic lights). */
export function isMacOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /mac/i.test(navigator.platform || navigator.userAgent);
}

/** Returns the platform-appropriate modifier symbol for display in shortcut hints. */
export function modifierKey(): string {
  return isMacOS() ? '⌘' : 'Ctrl';
}

/** Formats a keyboard shortcut for display, e.g. `['mod','k'] → "⌘K"`. */
export function formatShortcut(keys: readonly string[]): string {
  const mod = modifierKey();
  const sep = isMacOS() ? '' : '+';
  return keys
    .map((k) => {
      if (k === 'mod') return mod;
      if (k === 'shift') return isMacOS() ? '⇧' : 'Shift';
      if (k === 'alt') return isMacOS() ? '⌥' : 'Alt';
      return k.length === 1 ? k.toUpperCase() : k;
    })
    .join(sep);
}
