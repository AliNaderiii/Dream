/** Zustand persistence backed by tauri-plugin-store, with a browser fallback. */

import { LazyStore } from '@tauri-apps/plugin-store';
import type { StateStorage } from 'zustand/middleware';

import { isTauri } from '@/utils/platform';

const nativeStore = new LazyStore('layout.json', { autoSave: 80 });

/**
 * JSON strings are values inside Tauri's app-data store. In Vite/tests we use
 * localStorage so the same store remains directly exercisable in a browser.
 */
export const desktopStorage: StateStorage = {
  getItem: async (name) => {
    if (!isTauri()) return globalThis.localStorage?.getItem(name) ?? null;
    return (await nativeStore.get<string>(name)) ?? null;
  },
  setItem: async (name, value) => {
    if (!isTauri()) {
      globalThis.localStorage?.setItem(name, value);
      return;
    }
    await nativeStore.set(name, value);
  },
  removeItem: async (name) => {
    if (!isTauri()) {
      globalThis.localStorage?.removeItem(name);
      return;
    }
    await nativeStore.delete(name);
  },
};
