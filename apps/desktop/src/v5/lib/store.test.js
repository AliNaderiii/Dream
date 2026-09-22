import { beforeEach, describe, expect, it } from 'vitest';
import { createStore } from './store.js';

describe('createStore', () => {
  it('get returns the initial state', () => {
    const store = createStore({ view: 'chat', theme: 'dark' });
    expect(store.get()).toEqual({ view: 'chat', theme: 'dark' });
  });

  it('set patches shallowly and notifies subscribers', () => {
    const store = createStore({ n: 1, other: true });
    const seen = [];
    store.subscribe((s) => seen.push(s.n));
    store.set({ n: 2 });
    expect(store.get()).toEqual({ n: 2, other: true });
    expect(seen).toEqual([2]);
  });

  it('set accepts a function patch', () => {
    const store = createStore({ n: 1 });
    store.set((s) => ({ n: s.n + 41 }));
    expect(store.get().n).toBe(42);
  });

  it('unsubscribe stops notifications', () => {
    const store = createStore({ n: 0 });
    let calls = 0;
    const off = store.subscribe(() => (calls += 1));
    off();
    store.set({ n: 1 });
    expect(calls).toBe(0);
  });
});

describe('settings persistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('persists settings to localStorage on change', async () => {
    const { settings } = await import('./store.js');
    settings.set({ theme: 'light' });
    const raw = JSON.parse(localStorage.getItem('dream5:settings'));
    expect(raw.theme).toBe('light');
  });

  it('falls back to defaults when storage is empty', async () => {
    const { settings } = await import('./store.js');
    expect(['dark', 'light']).toContain(settings.get().theme);
    expect(typeof settings.get().onboarded).toBe('boolean');
  });
});
