import { afterEach, describe, expect, it } from 'vitest';

import { applyAppearance, resolveTheme } from '@/hooks/use-theme';

const base = {
  theme: 'light' as const,
  direction: 'ltr' as const,
  locale: 'en' as const,
  density: 'comfortable' as const,
  accent: 'violet' as const,
  zoom: 100,
  reduceMotion: false,
  numerals: 'latin' as const,
};

afterEach(() => {
  document.documentElement.removeAttribute('style');
});

describe('appearance engine', () => {
  it('applies a complete Warm theme snapshot atomically', () => {
    const resolved = applyAppearance({
      ...base,
      theme: 'warm',
      direction: 'rtl',
      locale: 'fa',
      density: 'dense',
      accent: 'forest',
      zoom: 125,
      reduceMotion: true,
      numerals: 'persian',
    });

    const root = document.documentElement;
    expect(resolved).toBe('warm');
    expect(root.dataset['theme']).toBe('warm');
    expect(root.dataset['accent']).toBe('forest');
    expect(root.dataset['density']).toBe('dense');
    expect(root.dataset['reduceMotion']).toBe('true');
    expect(root.dataset['numerals']).toBe('persian');
    expect(root.lang).toBe('fa');
    expect(root.dir).toBe('rtl');
    expect(root.style.getPropertyValue('--ui-scale')).toBe('1.25');
  });

  it('keeps Warm explicit instead of treating it as a system alias', () => {
    expect(resolveTheme('warm')).toBe('warm');
  });
});
