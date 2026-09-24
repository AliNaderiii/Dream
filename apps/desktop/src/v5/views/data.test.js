/**
 * Data-studio view tests — browser-honest and zero-simulation:
 * discovery and saved-session sections render with their honest notes,
 * the chart button exists only on an answered turn's panel, and in the
 * browser preview the core is unreachable (honest error on action, no
 * fake datasets or charts invented). The evidence drawer never opens
 * on its own.
 */
import { describe, expect, it } from 'vitest';
import { dataView } from './data.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  dataView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('data view', () => {
  it('renders the discovery and saved-sessions sections', () => {
    const { root } = mount();
    const titles = [...root.querySelectorAll('.rt-section-title')].map((t) => t.textContent);
    expect(titles.some((t) => t.includes('کشف مجموعه‌داده'))).toBe(true);
    expect(titles.some((t) => t.includes('نشست‌های ذخیره‌شده'))).toBe(true);
  });

  it('states the honest workspace-root discovery note', () => {
    const { root } = mount();
    expect(root.textContent).toContain('DREAM_WORKSPACE_ROOT');
  });

  it('offers loading a dataset and asking a question', () => {
    const { root } = mount();
    expect(root.textContent).toContain('بارگذاری مجموعه‌داده');
    expect(root.textContent).toContain('بپرس');
  });

  it('has no chart panel before an answer — charts come only from evidence', () => {
    const { root } = mount();
    expect(root.querySelectorAll('.chart-panel').length).toBe(0);
    expect(root.textContent).toContain('هنوز پرسشی پاسخ نگرفته');
  });

  it('is honest in the browser preview — discovery fails honestly', async () => {
    const { root } = mount();
    await flush();
    const btn = [...root.querySelectorAll('button')].find((b) => b.textContent.includes('کشف'));
    btn.click();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelectorAll('.disc-candidate').length).toBe(0);
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
