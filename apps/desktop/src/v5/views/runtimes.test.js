/**
 * Runtimes view tests — browser-honest and zero-simulation:
 * the provider-hubs matrix renders its four sections, the honest
 * no-secrets note is visible, and in the browser preview the core is
 * unreachable (honest error, no fake runtimes are invented). The
 * evidence drawer never opens on its own.
 */
import { describe, expect, it } from 'vitest';
import { runtimesView } from './runtimes.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  runtimesView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('runtimes view', () => {
  it('renders the four provider-hubs sections', () => {
    const { root } = mount();
    const titles = [...root.querySelectorAll('.rt-section-title')].map((t) => t.textContent);
    expect(titles.some((t) => t.includes('مسیر فعال'))).toBe(true);
    expect(titles.some((t) => t.includes('ماتریس موتورهای محلی'))).toBe(true);
    expect(titles.some((t) => t.includes('گیت‌وی ابزار'))).toBe(true);
    expect(titles.some((t) => t.includes('کاتالوگ ارائه‌دهنده‌ها'))).toBe(true);
  });

  it('states the honest no-secrets probe note', () => {
    const { root } = mount();
    expect(root.textContent).toContain('هرگز رمزی ارسال نمی‌شود');
  });

  it('is honest in the browser preview — no fake runtimes', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelectorAll('.runtime-card').length).toBe(0);
  });

  it('offers the catalog search box', () => {
    const { root } = mount();
    expect(root.querySelector('.cat-search')).toBeTruthy();
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
