/**
 * Code view tests — browser-honest: the sandbox lives in the desktop core,
 * nothing executes or is faked in the preview, no auto-evidence.
 */
import { describe, expect, it } from 'vitest';
import { codeView } from './code.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  codeView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('code view', () => {
  it('offers run + reset and states the real-execution promise', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('اجرا');
    expect(root.textContent).toContain('بازنشانی نشست');
    expect(root.textContent).toContain('اجرای واقعی پایتون');
  });

  it('says the desktop app is where the sandbox lives — never fakes output', async () => {
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
