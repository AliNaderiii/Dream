import { describe, expect, it } from 'vitest';

import { registeredNav, registeredRoutes, shellSlots } from './route-registry';

const PRE_P0_PATHS = new Set([
  '/',
  '/chat',
  '/memory',
  '/skills',
  '/projects',
  '/scheduler',
  '/subagents',
  '/provenance',
  '/data',
  '/connectivity',
  '/providers',
  '/settings',
]);

describe('route registry seam', () => {
  it('does not register any pre-P0 reserved path', () => {
    for (const route of registeredRoutes) {
      expect(PRE_P0_PATHS.has(route.path)).toBe(false);
    }
  });

  it('registers the P2 research route', () => {
    const research = registeredRoutes.find((r) => r.path === '/research');
    expect(research).toBeDefined();
    expect(research?.label).toBe('Research');
    expect(research?.group).toBe('workspace');
  });

  it('publishes only unique safe extension paths', () => {
    const safePath = /^\/[a-z][a-z0-9_-]*(?:\/[a-z0-9_:-]+)*$/;
    expect(new Set(registeredRoutes.map((route) => route.path)).size).toBe(registeredRoutes.length);
    expect(registeredRoutes.every((route) => safePath.test(route.path))).toBe(true);
    expect(registeredRoutes.map((route) => route.path)).not.toContain('/dashboard');
    expect(registeredRoutes.map((route) => route.path)).not.toContain('/chat');
  });

  it('exposes registered nav and shell slots consistently', () => {
    expect(registeredNav).toEqual(registeredRoutes);
    expect(shellSlots.main).toEqual(registeredRoutes);
  });
});
