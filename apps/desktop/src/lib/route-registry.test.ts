import { describe, expect, it } from 'vitest';

import { registeredRoutes } from './route-registry';

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

  it('registers the dataqa and research routes', () => {
    const dataqa = registeredRoutes.find((r) => r.path === '/dataqa');
    expect(dataqa).toBeDefined();
    expect(dataqa?.label).toBe('Data Q&A');
    expect(dataqa?.group).toBe('workspace');

    const research = registeredRoutes.find((r) => r.path === '/research');
    expect(research).toBeDefined();
    expect(research?.label).toBe('Research');
    expect(research?.group).toBe('workspace');

    const workspace = registeredRoutes.find((r) => r.path === '/workspace');
    expect(workspace).toBeDefined();
    expect(workspace?.label).toBe('Workspace');
    expect(workspace?.group).toBe('workspace');

    const agents = registeredRoutes.find((r) => r.path === '/agents');
    expect(agents).toBeDefined();
    expect(agents?.label).toBe('Agents');
    expect(agents?.group).toBe('workspace');
  });

  it('publishes only unique safe extension paths', () => {
    const safePath = /^\/[a-z][a-z0-9_-]*(?:\/[a-z0-9_:-]+)*$/;
    const paths = registeredRoutes.map((route) => route.path);
    expect(new Set(paths).size).toBe(paths.length);
    expect(paths.every((path) => safePath.test(path))).toBe(true);
    expect(paths).not.toContain('/dashboard');
    expect(paths).not.toContain('/chat');
  });
});
