/** Browser-honest research completion tests. */
import { describe, expect, it } from 'vitest';
import { researchView } from './research.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  researchView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('research completion actions', () => {
  it('renders the approval pipeline without inventing a report', () => {
    const { root } = mount();
    expect(root.textContent).toContain('تأیید صریح شما');
    expect(root.textContent).toContain('شروع پژوهش');
    expect(root.textContent).not.toContain('گزارش در هسته منتشر شد');
  });

  it('never opens evidence automatically', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
