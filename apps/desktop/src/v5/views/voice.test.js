/**
 * Voice view tests — both directions render honestly in the browser preview:
 * tabs exist, the STT pane works as before, and the TTS pane says the engines
 * live inside the desktop app instead of faking anything.
 */
import { describe, expect, it } from 'vitest';
import { voiceView } from './voice.js';
import { app, settings } from '../lib/store.js';

const flush = () => new Promise((r) => setTimeout(r, 20));

function mount() {
  const root = document.createElement('div');
  voiceView(root, { settings, app, openEvidence: () => {} });
  return root;
}

function tabButtons(root) {
  return [...root.querySelectorAll('.voice-tabs .voice-tab')];
}

describe('voice view', () => {
  it('renders both direction tabs', () => {
    const root = mount();
    const labels = tabButtons(root).map((b) => b.textContent);
    expect(labels.some((t) => t.includes('گفتار به متن'))).toBe(true);
    expect(labels.some((t) => t.includes('متن به گفتار'))).toBe(true);
  });

  it('keeps the STT drop zone in the default tab', () => {
    const root = mount();
    expect(root.textContent).toContain('فایل صوتی انتخاب کنید');
  });

  it('TTS pane is hidden until its tab is chosen', () => {
    const root = mount();
    const pane = root.querySelector('.voice-pane.hidden');
    expect(pane).not.toBeNull();
  });

  it('TTS tab shows the honest desktop-only notice — never fake audio', async () => {
    const root = mount();
    const ttsTab = tabButtons(root).find((b) => b.textContent.includes('متن به گفتار'));
    expect(ttsTab).toBeTruthy();
    ttsTab.click();
    await flush();
    const visibleText = root.textContent;
    expect(visibleText).toContain('دسکتاپ');
    // No audio element may exist without a real synthesis result.
    expect(root.querySelector('audio')).toBeNull();
  });

  it('settings carry honest tts defaults', () => {
    expect(settings.get().tts).toEqual({ engine: 'auto', voice: '', speed: 1 });
  });
});
