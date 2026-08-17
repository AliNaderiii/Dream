import '@testing-library/jest-dom/vitest';

import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

import i18n, { type InitOptions } from 'i18next';
import { initReactI18next } from 'react-i18next';

import { loadResources } from '@/lib/i18n/backend';
import { SUPPORTED_LOCALES } from '@/lib/i18n/locale-detector';

// Tests render components directly (no main.tsx bootstrap), so initialise the
// singleton i18next instance here, synchronously, before any test runs.
// `initImmediate` is a legacy i18next option still honoured at runtime but
// absent from the current `InitOptions` type, hence the cast.
void i18n.use(initReactI18next).init({
  resources: loadResources(),
  lng: 'en',
  fallbackLng: 'en',
  supportedLngs: [...SUPPORTED_LOCALES],
  returnEmptyString: false,
  returnNull: false,
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
  initImmediate: false,
} as unknown as InitOptions);

afterEach(() => {
  cleanup();
  localStorage.clear();
});

// jsdom implements neither matchMedia nor the layout APIs Radix probes.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

window.HTMLElement.prototype.scrollIntoView = vi.fn();
window.HTMLElement.prototype.releasePointerCapture = vi.fn();
window.HTMLElement.prototype.hasPointerCapture = vi.fn();
