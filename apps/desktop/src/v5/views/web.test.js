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

describe('web view tabs', () => {
  it('renders both the reading and the browser tab', () => {
    const { root } = mount();
    const tabs = [...root.querySelectorAll('.voice-tabs .voice-tab')].map((b) => b.textContent);
    expect(tabs.some((t) => t.includes('خواندن'))).toBe(true);
    expect(tabs.some((t) => t.includes('مرورگر'))).toBe(true);
  });

  it('browser pane is hidden until its tab is chosen', () => {
    const { root } = mount();
    const hiddenPane = root.querySelector('.web-pane.hidden');
    expect(hiddenPane).not.toBeNull();
    expect(hiddenPane.textContent).toContain('اتصال به کروم شما');
  });

  it('browser tab is honest in the preview — no fake pages, desktop-only', async () => {
    const { root } = mount();
    const tab = [...root.querySelectorAll('.voice-tabs .voice-tab')].find((b) =>
      b.textContent.includes('مرورگر'),
    );
    tab.click();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelector('.files-preview-text')).toBeNull();
  });
});

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
