/**
 * Web view tests — browser-honest: the human-in-the-loop promise is visible,
 * nothing is fetched or faked in the preview, no auto-evidence.
 */
import { describe, expect, it } from 'vitest';
import { webView } from './web.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  webView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('web view', () => {
  it('offers proposing a URL and states the approval rule', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('پیشنهاد');
    expect(root.textContent).toContain('بدون تأیید صریح شما');
  });

  it('says the desktop app is where the real fetch lives — never fakes a page', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelector('.files-preview-text')).toBeNull();
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
