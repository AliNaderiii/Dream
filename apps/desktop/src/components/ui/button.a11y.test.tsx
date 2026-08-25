import axe from 'axe-core';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Button } from './button';

async function violations(node: HTMLElement) {
  const result = await axe.run(node, {
    rules: {
      'color-contrast': { enabled: false },
    },
  });
  return result.violations;
}

describe('Button a11y', () => {
  it('has no axe violations for primary, secondary, destructive', async () => {
    const { container } = render(
      <main>
        <Button variant="primary">Save</Button>
        <Button variant="secondary">Cancel</Button>
        <Button variant="destructive">Delete</Button>
      </main>,
    );
    const v = await violations(container);
    expect(v).toHaveLength(0);
  });
});
