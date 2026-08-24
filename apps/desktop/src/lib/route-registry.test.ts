import { describe, expect, it } from 'vitest';

import { registeredNav, registeredRoutes, shellSlots } from './route-registry';

describe('route registry seam', () => {
  it('publishes deterministic, unique safe extension paths', () => {
    expect(Object.isFrozen(registeredRoutes)).toBe(true);
    expect(new Set(registeredRoutes.map((route) => route.path)).size).toBe(registeredRoutes.length);
    expect(shellSlots.main).toEqual(registeredRoutes);
    expect(registeredNav).toEqual(registeredRoutes);
  });
});
