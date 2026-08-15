import { afterEach, describe, expect, it, vi } from 'vitest';

import { formatShortcut, isTauri } from '@/utils/platform';

/** Overrides the reported platform for a single assertion. */
function mockPlatform(value: string) {
  Object.defineProperty(window.navigator, 'platform', { value, configurable: true });
}

describe('platform utils', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    mockPlatform('');
  });

  it('reports that it is not running under Tauri in tests', () => {
    expect(isTauri()).toBe(false);
  });

  it('formats shortcuts with the macOS command symbol', () => {
    mockPlatform('MacIntel');
    expect(formatShortcut(['mod', 'k'])).toBe('⌘K');
    expect(formatShortcut(['mod', 'shift', 'l'])).toBe('⌘⇧L');
  });

  it('formats shortcuts with Ctrl elsewhere', () => {
    mockPlatform('Win32');
    expect(formatShortcut(['mod', 'k'])).toBe('Ctrl+K');
  });
});
