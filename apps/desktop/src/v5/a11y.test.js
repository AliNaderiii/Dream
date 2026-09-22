/**
 * Accessibility gate for v5 — real, CI-able checks:
 * 1. WCAG contrast ratios computed from the actual design tokens
 *    (both themes): body text, secondary text, and the accent on surfaces.
 * 2. Structural checks: RTL Persian document, aria-hidden icons,
 *    visible focus styles.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const V5 = resolve(dirname(fileURLToPath(import.meta.url)));
const APP = resolve(V5, '..', '..');

function read(rel) {
  return readFileSync(resolve(APP, rel), 'utf8');
}

/** Parse `--name: #hex;` (and rgba()) pairs out of a CSS variable block. */
function parseVars(css) {
  const vars = {};
  for (const m of css.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    vars[m[1]] = m[2].trim();
  }
  return vars;
}

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h;
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

function luminance({ r, g, b }) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(fg, bg) {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

function tokensByTheme() {
  const css = read('src/v5/styles/tokens.css');
  const darkMatch = css.match(/:root\s*\{([\s\S]*?)\n\}/);
  const lightMatch = css.match(/\[data-theme='light'\]\s*\{([\s\S]*?)\n\}/);
  return { dark: parseVars(darkMatch[1]), light: parseVars(lightMatch[1]) };
}

describe('WCAG contrast (computed from real tokens)', () => {
  for (const [theme, vars] of Object.entries(tokensByTheme())) {
    it(`${theme}: body text on app background ≥ 7 (AAA)`, () => {
      const ratio = contrast(hexToRgb(vars['tx-0']), hexToRgb(vars['bg-0']));
      expect(ratio).toBeGreaterThanOrEqual(7);
    });

    it(`${theme}: secondary text on panels ≥ 4.5 (AA)`, () => {
      const ratio = contrast(hexToRgb(vars['tx-1']), hexToRgb(vars['bg-1']));
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it(`${theme}: accent on app background ≥ 3 (UI components)`, () => {
      const ratio = contrast(hexToRgb(vars['accent']), hexToRgb(vars['bg-0']));
      expect(ratio).toBeGreaterThanOrEqual(3);
    });

    it(`${theme}: ink on accent buttons ≥ 3`, () => {
      const ratio = contrast(hexToRgb(vars['accent-ink']), hexToRgb(vars['accent']));
      expect(ratio).toBeGreaterThanOrEqual(3);
    });
  }
});

describe('structural accessibility', () => {
  it('the document is RTL Persian', () => {
    const html = read('index.html');
    expect(html).toMatch(/<html[^>]*lang="fa"[^>]*dir="rtl"/);
  });

  it('every rendered icon is an aria-hidden svg', async () => {
    const { ic, icons } = await import('./lib/icons.js');
    const names = Object.keys(icons);
    expect(names.length).toBeGreaterThan(10);
    for (const name of names) {
      const svg = ic(name);
      expect(svg.startsWith('<svg')).toBe(true);
      expect(svg).toContain('aria-hidden="true"');
    }
    // Unknown names degrade to an empty string, never a broken glyph.
    expect(ic('does-not-exist')).toBe('');
  });

  it('focus styles exist (keyboard users are first-class)', () => {
    const base = read('src/v5/styles/base.css');
    expect(base).toMatch(/:focus-visible/);
  });

  it('reduced data: no external font/CDN fetches — everything is local', () => {
    for (const rel of ['index.html', 'src/v5/styles/base.css', 'src/v5/styles/tokens.css']) {
      const src = read(rel);
      expect(src).not.toMatch(/https?:\/\/[^ "']*\.(woff|ttf|css|js)/);
    }
  });
});
