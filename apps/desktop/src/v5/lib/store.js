/**
 * Tiny observable store + localStorage persistence.
 * No framework state manager — get / set / subscribe is all the app needs.
 */

export function createStore(initial) {
  let state = initial;
  const listeners = new Set();
  return {
    get: () => state,
    set(patch) {
      const next = typeof patch === 'function' ? patch(state) : patch;
      state = { ...state, ...next };
      for (const fn of listeners) fn(state);
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

function load(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return { ...fallback, ...JSON.parse(raw) };
  } catch {
    return fallback;
  }
}

/**
 * The persisted app settings. Shape:
 * {
 *   theme: 'dark' | 'light',
 *   onboarded: boolean,
 *   view: string,
 *   model: { provider: 'none'|'ollama'|'openai', baseUrl, apiKey, model },
 *   tts: { engine: 'auto'|'edge'|'piper', voice, speed }
 * }
 */
export const settings = createStore(
  load('dream5:settings', {
    theme: 'dark',
    onboarded: false,
    view: 'chat',
    model: { provider: 'none', baseUrl: '', apiKey: '', model: '' },
    tts: { engine: 'auto', voice: '', speed: 1 },
  }),
);

settings.subscribe((state) => {
  try {
    localStorage.setItem('dream5:settings', JSON.stringify(state));
  } catch {
    /* storage unavailable — settings stay in-memory */
  }
});

/** Ephemeral (non-persisted) app state: bridge status, view routing. */
export const app = createStore({
  bridge: 'unknown', // 'ready' | 'down' | 'browser'
  view: 'chat',
  evidence: null, // evidence object shown in the drawer
});
