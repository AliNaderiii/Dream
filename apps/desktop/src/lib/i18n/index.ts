/**
 * i18n bootstrap and React bindings.
 *
 * One i18next instance drives the whole shell. The zustand `useAppStore` is the
 * source of truth for the active locale (so it persists across restarts and
 * also drives the `dir`/`lang` attributes on `<html>`); this module keeps
 * i18next synchronised with it and exposes the `t`/`useTranslation` bindings
 * every component uses.
 */

import { useEffect } from 'react';
import i18n from 'i18next';
import { initReactI18next, useTranslation } from 'react-i18next';

import { useAppStore } from '@/stores/use-app-store';
import type { Locale } from '@/types';

import { loadResources } from './backend';
import { detectLocale, isRtlLocale, SUPPORTED_LOCALES } from './locale-detector';

/** The name the zustand persist middleware writes under. */
const PERSIST_KEY = 'dream.app';

/** Flag emoji + native name for the language picker. */
export const LANGUAGES: ReadonlyArray<{ code: Locale; flag: string; nameKey: string }> = [
  { code: 'en', flag: '🇬🇧', nameKey: 'language.en' },
  { code: 'fa', flag: '🇮🇷', nameKey: 'language.fa' },
  { code: 'zh-CN', flag: '🇨🇳', nameKey: 'language.zh-CN' },
  { code: 'ja', flag: '🇯🇵', nameKey: 'language.ja' },
  { code: 'es', flag: '🇪🇸', nameKey: 'language.es' },
  { code: 'de', flag: '🇩🇪', nameKey: 'language.de' },
  { code: 'fr', flag: '🇫🇷', nameKey: 'language.fr' },
  { code: 'ko', flag: '🇰🇷', nameKey: 'language.ko' },
];

let initialised = false;

/**
 * The locale to start the app with.
 *
 * A first-ever launch (no persisted app state) auto-detects from
 * `navigator.language`; once the user has picked a language that choice is
 * honoured on every subsequent launch.
 */
export function resolveInitialLocale(): Locale {
  const detected = detectLocale();
  if (typeof localStorage === 'undefined') return detected;

  try {
    const raw = localStorage.getItem(PERSIST_KEY);
    if (raw) {
      const persisted = JSON.parse(raw) as { state?: { locale?: string } };
      if (persisted.state?.locale && isSupportedLocale(persisted.state.locale)) {
        return persisted.state.locale;
      }
    }
  } catch {
    // Corrupt persistence → fall through to detection.
  }
  return detected;
}

function isSupportedLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/** Initialise the singleton i18next instance with the given starting locale. */
export async function initI18n(locale?: Locale): Promise<typeof i18n> {
  if (!initialised) {
    await i18n.use(initReactI18next).init({
      resources: loadResources(),
      lng: locale ?? resolveInitialLocale(),
      fallbackLng: 'en',
      supportedLngs: SUPPORTED_LOCALES,
      // Missing keys render the key itself (never a raw English value), so a
      // dropped translation is visible instead of silently wrong.
      returnEmptyString: false,
      returnNull: false,
      interpolation: { escapeValue: false }, // React already escapes.
      react: { useSuspense: false },
    });
    initialised = true;
  }
  return i18n;
}

/**
 * Keep i18next's language in lockstep with the store. Mount once near the app
 * root (the app shell); `main.tsx` seeds the store with the detected locale
 * before the first render.
 */
export function useLocaleSync(): void {
  const locale = useAppStore((s) => s.locale);
  useEffect(() => {
    void i18n.changeLanguage(locale);
  }, [locale]);
}

export { i18n, isRtlLocale, SUPPORTED_LOCALES, useTranslation };
export { detectLocale } from './locale-detector';
export type { Locale };
