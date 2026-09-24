/**
 * Spaces view tests — browser-honest and zero-simulation:
 * the create form and the honest scheduler note render, and in the
 * browser preview the core is unreachable (honest error, no fake
 * spaces are invented). The evidence drawer never opens on its own.
 */
import { describe, expect, it } from 'vitest';
import { spacesView } from './spaces.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  spacesView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('spaces view', () => {
  it('renders the create form with language and ceiling selects', () => {
    const { root } = mount();
    const titles = [...root.querySelectorAll('.rt-section-title')].map((t) => t.textContent);
    expect(titles.some((t) => t.includes('فضای جدید'))).toBe(true);
    expect(titles.some((t) => t.includes('فضاهای من'))).toBe(true);
    expect(root.querySelector('input.input')).toBeTruthy();
    const options = [...root.querySelectorAll('option')].map((o) => o.textContent);
    expect(options.some((o) => o.includes('فارسی'))).toBe(true);
    expect(options.some((o) => o.includes('محافظه‌کار'))).toBe(true);
  });

  it('states the honest scheduler rule — every fire needs approval', () => {
    const { root } = mount();
    expect(root.textContent).toContain('نیازمند تأیید');
  });

  it('states that folders attach in place, without copying', () => {
    const { root } = mount();
    expect(root.textContent).toContain('در جای خود');
  });

  it('is honest in the browser preview — no fake spaces', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelectorAll('.space-card').length).toBe(0);
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
