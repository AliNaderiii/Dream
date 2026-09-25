/** Browser-honest episodic operation tests. */
import { describe, expect, it } from 'vitest';
import { memoryView } from './memory.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  memoryView(root, { app, settings });
  return root;
}

describe('memory operations', () => {
  it('offers explicit compression and consolidation actions', () => {
    const root = mount();
    expect(root.textContent).toContain('فشرده‌سازی نشست');
    expect(root.textContent).toContain('تثبیت حافظه بلندمدت');
    expect(root.textContent).toContain('فقط با انتخاب صریح شما');
  });

  it('shows no invented operation result in the browser', async () => {
    const root = mount();
    await flush();
    expect(root.textContent).not.toContain('اپیزود واقعی ساخته شد');
    expect(root.textContent).not.toContain('تثبیت واقعی انجام شد');
  });
});
