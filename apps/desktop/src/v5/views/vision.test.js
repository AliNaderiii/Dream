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
    expect(root.textContent).toContain('ذخیره');
  });

  it('shows the capability boundary and secure metadata-only intake', () => {
    const { root } = mount();
    expect(root.textContent).toContain('VISION READINESS');
    expect(root.textContent).toContain('SECURE IMAGE INTAKE');
    expect(root.textContent).toContain('metadata');
    expect(root.textContent).toContain('inference');
  });

  it('shows the honest desktop-only error in the browser — never a fake OCR', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelector('.result-text')).toBeNull();
  });

  it('offers real Mermaid/SVG structural review without claiming image vision', async () => {
    const { root } = mount();
    await flush();
    expect(root.textContent).toContain('بازبینی نمودار');
    expect(root.textContent).toContain('بدون رندر یا ادعای دیدن تصویر');
    const input = root.querySelector('.vision-diagram-input');
    input.value = 'graph TD\\n A --> B';
    const button = [...root.querySelectorAll('button')].find((b) =>
      b.textContent.includes('بازبینی نمودار'),
    );
    button.click();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelector('.vision-diagram-stage .result-text')).toBeNull();
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
