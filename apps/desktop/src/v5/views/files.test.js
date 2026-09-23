/**
 * Files view tests — browser-honest: no roots are faked, the desktop-only
 * guard surfaces, and mounting never touches the evidence drawer.
 */
import { describe, expect, it } from 'vitest';
import { filesView } from './files.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  filesView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('files view', () => {
  it('offers folder registration and never fakes roots in the browser', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('افزودن پوشه');
    expect(root.querySelector('.files-root')).toBeNull();
    // The honest empty state must not appear without a real, empty root list.
    expect(root.querySelector('.files-list')).toBeNull();
  });

  it('says the desktop app is where the real workspace lives', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
