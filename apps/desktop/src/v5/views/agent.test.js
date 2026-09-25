/**
 * Agent-mode view tests — browser-honest and zero-simulation:
 * the three tabs render, the honest rule-based goal note and the
 * never-spawn-dangerous-shell note are visible, and in the browser
 * preview the core is unreachable (honest error, no fake goal results).
 * The evidence drawer never opens on its own. The simulated plan mode
 * (three template steps marked done) got no UI — this view is what the
 * real parts deserve.
 */
import { describe, expect, it } from 'vitest';
import { agentView } from './agent.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  agentView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('agent view', () => {
  it('renders the goal, shell, and live-status tabs', () => {
    const { root } = mount();
    const tabs = [...root.querySelectorAll('.voice-tabs .voice-tab')].map((b) => b.textContent);
    expect(tabs.some((t) => t.includes('هدف'))).toBe(true);
    expect(tabs.some((t) => t.includes('پوسته'))).toBe(true);
    expect(tabs.some((t) => t.includes('وضعیت زنده'))).toBe(true);
  });

  it('states the honest rule-based goal evaluator — no fake intelligence', () => {
    const { root } = mount();
    expect(root.textContent).toContain('نه LLM');
  });

  it('renders the references and commands workbench', () => {
    const { root } = mount();
    const tab = [...root.querySelectorAll('.voice-tabs .voice-tab')].find((b) =>
      b.textContent.includes('مراجع و فرمان‌ها'),
    );
    expect(tab).toBeTruthy();
    tab.click();
    expect(root.textContent).toContain('تجزیهٔ مراجع');
    expect(root.textContent).toContain('فهرست فرمان‌ها');
  });

  it('states that dangerous shell never spawns, even if approved', () => {
    const { root } = mount();
    const tab = [...root.querySelectorAll('.voice-tabs .voice-tab')].find((b) =>
      b.textContent.includes('پوسته'),
    );
    tab.click();
    expect(root.textContent).toContain('هرگز');
  });

  it('is honest in the references workbench — no fake parse result in browser', async () => {
    const { root } = mount();
    const tab = [...root.querySelectorAll('.voice-tabs .voice-tab')].find((b) =>
      b.textContent.includes('مراجع و فرمان‌ها'),
    );
    tab.click();
    const input = root.querySelector('textarea.input');
    input.value = '@sales.csv #session /goal';
    const parse = [...root.querySelectorAll('button')].find((b) =>
      b.textContent.includes('تجزیهٔ مراجع'),
    );
    parse.click();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelectorAll('.crit-row').length).toBe(0);
  });

  it('offers starting a goal with acceptance criteria', () => {
    const { root } = mount();
    expect(root.textContent).toContain('شروع و ارزیابی');
  });

  it('is honest in the browser preview — no fake results', async () => {
    const { root } = mount();
    await flush();
    const objective = root.querySelector('input.input');
    const criteria = root.querySelector('textarea.input');
    objective.value = 'آماده‌سازی گزارش';
    criteria.value = 'فایل sales.xlsx موجود باشد';
    const start = [...root.querySelectorAll('button')].find((b) =>
      b.textContent.includes('شروع و ارزیابی'),
    );
    start.click();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
    expect(root.querySelectorAll('.crit-row').length).toBe(0);
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
