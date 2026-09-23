/**
 * Vision view tests — browser-honest: the privacy promise is visible,
 * nothing is captured or faked in the preview, and no auto-evidence.
 */
import { describe, expect, it } from 'vitest';
import { visionView } from './vision.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  visionView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('vision view', () => {
  it('shows the capture affordance with the privacy note', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('عکس‌گرفتن از صفحه');
    expect(root.textContent).toContain('ذخیره نمی‌شوند');
  });

  it('shows the honest desktop-only error in the browser — never a fake OCR', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelector('.result-text')).toBeNull();
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
