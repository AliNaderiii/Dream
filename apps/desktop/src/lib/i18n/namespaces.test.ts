import { describe, expect, it } from 'vitest';

import { registeredNamespaces } from './namespaces';

describe('locale namespace seam', () => {
  it('discovers the bundled namespaces once in sorted order', () => {
    expect(registeredNamespaces).toContain('common');
    expect(registeredNamespaces).toEqual([...registeredNamespaces].sort());
    expect(new Set(registeredNamespaces).size).toBe(registeredNamespaces.length);
  });
});
