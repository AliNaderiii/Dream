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
const loadedLocales = new Set<string>();

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

/** Load a locale from bundled Tauri assets once, then register every namespace. */
export async function ensureLocale(locale: Locale): Promise<void> {
  if (loadedLocales.has(locale) || i18n.hasResourceBundle(locale, 'common')) {
    loadedLocales.add(locale);
    return;
  }
  const resources = await loadResources([locale]);
  const namespaces = resources[locale] ?? {};
  Object.entries(namespaces).forEach(([namespace, bundle]) => {
    i18n.addResourceBundle(locale, namespace, bundle, true, true);
  });
  loadedLocales.add(locale);
}

/** Initialise the singleton i18next instance with the given starting locale. */
export async function initI18n(locale?: Locale): Promise<typeof i18n> {
  if (!initialised) {
    const initialLocale = locale ?? resolveInitialLocale();
    const startupLocales =
      import.meta.env.MODE === 'test'
        ? SUPPORTED_LOCALES
        : initialLocale === 'en'
          ? ['en']
          : ['en', initialLocale];
    const resources = await loadResources(startupLocales);
    startupLocales.forEach((loadedLocale) => loadedLocales.add(loadedLocale));
    await i18n.use(initReactI18next).init({
      resources,
      lng: initialLocale,
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
    if (i18n.resolvedLanguage === locale) return;
    if (i18n.hasResourceBundle(locale, 'common')) {
      void i18n.changeLanguage(locale);
      return;
    }
    let current = true;
    void ensureLocale(locale).then(() => {
      if (current) return i18n.changeLanguage(locale);
    });
    return () => {
      current = false;
    };
  }, [locale]);
}

export { i18n, isRtlLocale, SUPPORTED_LOCALES, useTranslation };
export { detectLocale } from './locale-detector';
export type { Locale };
