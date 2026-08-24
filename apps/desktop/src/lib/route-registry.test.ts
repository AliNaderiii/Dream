import { describe, expect, it } from 'vitest';

import { registeredNav, registeredRoutes, shellSlots } from './route-registry';

describe('route registry seam', () => {
  it('does not register any pre-P0 route on the current tree', () => {
    expect(registeredRoutes).toEqual([]);
    expect(registeredNav).toEqual([]);
    expect(shellSlots.main).toEqual([]);
  });

  it('publishes only unique safe extension paths', () => {
    const safePath = /^\/[a-z][a-z0-9_-]*(?:\/[a-z0-9_:-]+)*$/;
    expect(new Set(registeredRoutes.map((route) => route.path)).size).toBe(registeredRoutes.length);
    expect(registeredRoutes.every((route) => safePath.test(route.path))).toBe(true);
    expect(registeredRoutes.map((route) => route.path)).not.toContain('/dashboard');
    expect(registeredRoutes.map((route) => route.path)).not.toContain('/chat');
  });
});
