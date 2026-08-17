/**
 * Navigator-language detection and locale helpers.
 *
 * Maps the browser's `navigator.language` (which is far more specific, e.g.
 * `fa-IR` or `zh-Hant-TW`) onto the finite set of locales Dream ships.
 */

import type { Locale } from '@/types';

/** Every locale Dream ships, in display order. */
export const SUPPORTED_LOCALES: readonly Locale[] = [
  'en',
  'fa',
  'zh-CN',
  'ja',
  'es',
  'de',
  'fr',
  'ko',
];

/** Languages written right-to-left (only Persian today). */
const RTL_LOCALES: readonly Locale[] = ['fa'];

/** Base-language tag → the locale Dream ships for it. */
const BASE_TO_LOCALE: Record<string, Locale> = {
  en: 'en',
  fa: 'fa',
  zh: 'zh-CN',
  ja: 'ja',
  es: 'es',
  de: 'de',
  fr: 'fr',
  ko: 'ko',
};

/** True when the locale renders right-to-left. */
export function isRtlLocale(locale: Locale): boolean {
  return RTL_LOCALES.includes(locale);
}

/** Strip a region/script tag to its base language, e.g. `zh-Hant-TW` → `zh`. */
function baseLanguage(tag: string): string {
  return tag.toLowerCase().split('-')[0];
}

/**
 * Resolve a raw language tag to a supported locale, falling back to English.
 *
 * `navigator.language` is read defensively so this is safe in jsdom (where the
 * property is absent) and during SSR.
 */
export function detectLocale(tag?: string): Locale {
  const raw = tag ?? (typeof navigator !== 'undefined' ? navigator.language : 'en');
  if (!raw) return 'en';

  // Exact match first (e.g. `zh-CN`), then base-language match (e.g. `fa-IR`).
  const lower = raw.toLowerCase().replace('_', '-');
  if ((SUPPORTED_LOCALES as readonly string[]).includes(lower)) return lower as Locale;
  return BASE_TO_LOCALE[baseLanguage(lower)] ?? 'en';
}
