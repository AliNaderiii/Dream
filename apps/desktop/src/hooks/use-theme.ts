/**
 * Theme and direction engine.
 *
 * Applies `data-theme`, `dir`, `lang` and `data-density` to `<html>` and keeps
 * `system` theme in sync with the OS via `prefers-color-scheme`.
 */

import { useEffect } from 'react';

import { useAppStore } from '@/stores/use-app-store';
import type { ResolvedTheme } from '@/types';

/** Reads the OS colour preference; defaults to light where unsupported. */
function systemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/**
 * Synchronises store state to the document. Mount once, at the app root.
 */
export function useTheme(): void {
  const theme = useAppStore((s) => s.theme);
  const direction = useAppStore((s) => s.direction);
  const locale = useAppStore((s) => s.locale);
  const density = useAppStore((s) => s.density);
  const setResolvedTheme = useAppStore((s) => s.setResolvedTheme);

  useEffect(() => {
    const apply = () => {
      const resolved: ResolvedTheme = theme === 'system' ? systemTheme() : theme;
      document.documentElement.setAttribute('data-theme', resolved);
      setResolvedTheme(resolved);
    };

    apply();

    // Only `system` needs to track OS changes.
    if (theme !== 'system' || !window.matchMedia) return;

    const query = window.matchMedia('(prefers-color-scheme: dark)');
    query.addEventListener('change', apply);
    return () => query.removeEventListener('change', apply);
  }, [theme, setResolvedTheme]);

  useEffect(() => {
    document.documentElement.setAttribute('dir', direction);
    document.documentElement.setAttribute('lang', locale);
  }, [direction, locale]);

  useEffect(() => {
    document.documentElement.setAttribute('data-density', density);
  }, [density]);
}
