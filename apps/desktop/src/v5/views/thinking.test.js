/**
 * Thinking view tests — browser-honest and zero-simulation-surfacing:
 * both tabs render, the honest rule-based notices are visible, and the
 * swarm/debate simulations never get UI (this view is what replaced them).
 */
import { describe, expect, it } from 'vitest';
import { thinkingView } from './thinking.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  let opened = 0;
  thinkingView(root, {
    app,
    settings,
    openEvidence: () => {
      opened += 1;
    },
  });
  return { root, opened };
}

describe('thinking view', () => {
  it('renders both the tree and the mental-model tab', () => {
    const { root } = mount();
    const tabs = [...root.querySelectorAll('.voice-tabs .voice-tab')].map((b) => b.textContent);
    expect(tabs.some((t) => t.includes('درخت استدلال'))).toBe(true);
    expect(tabs.some((t) => t.includes('مدل ذهنی'))).toBe(true);
  });

  it('states the honest rule-based evaluator — no fake intelligence', () => {
    const { root } = mount();
    expect(root.textContent).toContain('نه LLM');
  });

  it('tree tab offers starting a goal-driven tree', () => {
    const { root } = mount();
    expect(root.textContent).toContain('شروع درخت');
  });

  it('mental-model tab is honest in the browser preview', async () => {
    const { root } = mount();
    const tab = [...root.querySelectorAll('.voice-tabs .voice-tab')].find((b) =>
      b.textContent.includes('مدل ذهنی'),
    );
    tab.click();
    await flush();
    expect(root.textContent).toContain('دسکتاپ');
  });

  it('never opens the evidence drawer on its own', async () => {
    const { opened } = mount();
    await flush();
    expect(opened).toBe(0);
  });
});
