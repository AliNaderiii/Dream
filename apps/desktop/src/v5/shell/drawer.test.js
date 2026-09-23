/**
 * Regression tests for the evidence drawer geometry bug (v5.0.0–v5.1.0):
 * the closed-state transforms were swapped, so in RTL the "closed" drawer
 * sat 400px INSIDE the viewport — a dead panel over the middle of every
 * view, swallowing clicks. The drawer must be fully off-screen (and
 * invisible) until the user opens it.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { chatView } from '../views/chat.js';
import { voiceView } from '../views/voice.js';
import { app, settings } from '../lib/store.js';

const css = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '..', 'styles', 'shell.css'),
  'utf8',
);

function block(selector) {
  const re = new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}');
  const m = css.match(re);
  expect(m, `rule ${selector} must exist in shell.css`).not.toBeNull();
  return m[1];
}

describe('evidence drawer geometry (RTL regression)', () => {
  it('hidden state moves the drawer PAST its inline-end edge (positive X in LTR)', () => {
    expect(block('.drawer')).toMatch(/transform:\s*translateX\(105%\)/);
  });

  it('RTL hidden state moves it past the LEFT edge (negative physical X)', () => {
    expect(block("[dir='rtl'] .drawer")).toMatch(/transform:\s*translateX\(-105%\)/);
  });

  it('the open state brings it back on-screen and visible', () => {
    expect(block('.drawer.open')).toMatch(/transform:\s*translateX\(0\)/);
    expect(block('.drawer.open')).toMatch(/visibility:\s*visible/);
  });

  it('the closed drawer is invisible to pointer and assistive tech, not just moved', () => {
    expect(block('.drawer')).toMatch(/visibility:\s*hidden/);
  });
});

describe('nothing opens by itself', () => {
  it('the chat tools menu starts hidden', () => {
    const root = document.createElement('div');
    chatView(root, { app, settings, openEvidence: () => {} });
    const menu = root.querySelector('.tools-menu');
    expect(menu).not.toBeNull();
    expect(menu.classList.contains('hidden')).toBe(true);
  });

  it('mounting the voice view never opens the evidence drawer', () => {
    let opened = 0;
    const root = document.createElement('div');
    voiceView(root, {
      app,
      settings,
      openEvidence: () => {
        opened += 1;
      },
    });
    expect(opened).toBe(0);
  });
});
