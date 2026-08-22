/**
 * Appearance engine: theme, accent, script direction, density, zoom and motion.
 * All changes are attributes/custom properties on `<html>`, so locale and
 * direction switches never remount the React tree or flash an intermediate UI.
 */

import { useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';

import { useAppStore } from '@/stores/use-app-store';
import type {
  Accent,
  Density,
  Direction,
  Locale,
  NumeralStyle,
  ResolvedTheme,
  ThemeMode,
} from '@/types';

interface AppearanceSnapshot {
  theme: ThemeMode;
  direction: Direction;
  locale: Locale;
  density: Density;
  accent: Accent;
  zoom: number;
  reduceMotion: boolean;
  numerals: NumeralStyle;
}

/** Reads the OS colour preference; warm remains an explicit user choice. */
export function systemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function resolveTheme(theme: ThemeMode): ResolvedTheme {
  return theme === 'system' ? systemTheme() : theme;
}

/** Apply the complete snapshot in one synchronous DOM write batch. */
export function applyAppearance(snapshot: AppearanceSnapshot): ResolvedTheme {
  const root = document.documentElement;
  const resolved = resolveTheme(snapshot.theme);
  root.dataset['theme'] = resolved;
  root.dataset['accent'] = snapshot.accent;
  root.dataset['density'] = snapshot.density;
  root.dataset['reduceMotion'] = String(snapshot.reduceMotion);
  root.dataset['numerals'] = snapshot.numerals;
  root.dir = snapshot.direction;
  root.lang = snapshot.locale;
  root.style.setProperty('--ui-scale', String(snapshot.zoom / 100));
  return resolved;
}

/** Synchronises the persisted appearance store to the document. Mount once. */
export function useTheme(): void {
  const snapshot = useAppStore(
    useShallow((state) => ({
      theme: state.theme,
      direction: state.direction,
      locale: state.locale,
      density: state.density,
      accent: state.accent,
      zoom: state.zoom,
      reduceMotion: state.reduceMotion,
      numerals: state.numerals,
    })),
  );
  const setResolvedTheme = useAppStore((state) => state.setResolvedTheme);

  useEffect(() => {
    setResolvedTheme(applyAppearance(snapshot));
  }, [setResolvedTheme, snapshot]);

  useEffect(() => {
    if (snapshot.theme !== 'system' || !window.matchMedia) return;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const applySystemChange = () => setResolvedTheme(applyAppearance(snapshot));
    query.addEventListener('change', applySystemChange);
    return () => query.removeEventListener('change', applySystemChange);
  }, [setResolvedTheme, snapshot]);
}
