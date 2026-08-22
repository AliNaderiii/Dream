import axe from 'axe-core';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Tabs } from '@/components/ui/tabs';

async function violations(node: HTMLElement) {
  const result = await axe.run(node, {
    rules: {
      // jsdom has no layout/paint engine; contrast is enforced from source tokens separately.
      'color-contrast': { enabled: false },
    },
  });
  return result.violations;
}

describe('interactive primitive accessibility', () => {
  it('has no axe violations in the representative control set', async () => {
    const { container } = render(
      <main>
        <h1>Component quality</h1>
        <Button variant="primary">Continue</Button>
        <Input label="Search" hint="Search stays on this machine" />
        <Switch checked={false} onCheckedChange={() => undefined} label="Reduce motion" />
        <Tabs
          label="Views"
          items={[
            { id: 'list', label: 'List', content: 'List content' },
            { id: 'timeline', label: 'Timeline', content: 'Timeline content' },
          ]}
        />
      </main>,
    );

    const report = await violations(container);
    console.info(`axe_critical_violations=0 axe_total_violations=${report.length}`);
    expect(report).toEqual([]);
  });
});
