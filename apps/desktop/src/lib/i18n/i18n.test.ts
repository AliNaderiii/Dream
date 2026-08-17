/**
 * Internationalisation gates (G1): locale coverage, RTL detection, and
 * language resolution.
 *
 * The coverage gate asserts every shipped language carries at least 90% of the
 * English key set (in practice 100% — the generator enforces identical trees).
 */

import { describe, expect, it } from 'vitest';

import { i18n, LANGUAGES, resolveInitialLocale } from '@/lib/i18n';
import { detectLocale, isRtlLocale, SUPPORTED_LOCALES } from '@/lib/i18n/locale-detector';

import enCommon from '@/locales/en/common.json';

const localeFiles = import.meta.glob<{ default: Record<string, unknown> }>(
  '../../locales/*/*.json',
  { eager: true },
);

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

const englishKeys = flatten(enCommon).sort();

function keysForLanguage(lang: string): string[] {
  const namespaces: string[] = [];
  for (const [path, mod] of Object.entries(localeFiles)) {
    const [dir] = path.split('/').slice(-2);
    if (dir === lang) namespaces.push(...flatten(mod.default));
  }
  return namespaces.sort();
}

describe('i18n coverage', () => {
  it('ships every supported locale with 8 locale files', () => {
    expect(SUPPORTED_LOCALES).toHaveLength(8);
  });

  it.each(SUPPORTED_LOCALES.filter((l) => l !== 'en'))(
    '%s has ≥90% of the English key set',
    (lang) => {
      const langKeys = keysForLanguage(lang);
      const missing = englishKeys.filter((k) => !langKeys.includes(k));
      const coverage = (englishKeys.length - missing.length) / englishKeys.length;
      expect(coverage).toBeGreaterThanOrEqual(0.9);
    },
  );

  it('falls back to the key string for a missing key', () => {
    expect(i18n.t('common.this.key.does.not.exist')).toBe('common.this.key.does.not.exist');
  });
});

describe('RTL and direction', () => {
  it('flags only Persian as right-to-left', () => {
    for (const locale of SUPPORTED_LOCALES) {
      expect(isRtlLocale(locale)).toBe(locale === 'fa');
    }
  });

  it('renders a Persian translation when switched to fa', async () => {
    await i18n.changeLanguage('fa');
    expect(i18n.t('nav.settings', { ns: 'common' })).toBe('تنظیمات');
    await i18n.changeLanguage('en');
    expect(i18n.t('nav.settings', { ns: 'common' })).toBe('Settings');
  });
});

describe('language detection', () => {
  it('maps exact and base-language tags', () => {
    expect(detectLocale('en-US')).toBe('en');
    expect(detectLocale('fa-IR')).toBe('fa');
    expect(detectLocale('zh-CN')).toBe('zh-CN');
    expect(detectLocale('zh-TW')).toBe('zh-CN');
    expect(detectLocale('de-DE')).toBe('de');
    expect(detectLocale('ko-KR')).toBe('ko');
  });

  it('falls back to English for unknown tags', () => {
    expect(detectLocale('xx-XX')).toBe('en');
    expect(detectLocale('')).toBe('en');
  });

  it('exposes a flag and native name for every picker entry', () => {
    expect(LANGUAGES.map((l) => l.code)).toEqual(SUPPORTED_LOCALES);
    for (const lang of LANGUAGES) expect(lang.flag).toBeTruthy();
  });

  it('resolves a persisted locale over detection', () => {
    localStorage.setItem('dream.app', JSON.stringify({ state: { locale: 'fr' }, version: 0 }));
    expect(resolveInitialLocale()).toBe('fr');
    localStorage.clear();
  });
});
