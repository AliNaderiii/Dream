import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs } from '@/components/ui/tabs';
import { ToastViewport } from '@/components/ui/toast';

const fixtures: Array<[string, ReactElement]> = [];
for (const variant of ['primary', 'secondary', 'ghost', 'destructive', 'danger-outline'] as const) {
  for (const size of ['sm', 'md', 'lg'] as const) {
    fixtures.push([
      `button-${variant}-${size}`,
      <Button variant={variant} size={size}>
        Action
      </Button>,
    ]);
  }
}
for (const variant of ['neutral', 'accent', 'success', 'warning', 'danger', 'info'] as const) {
  fixtures.push([`badge-${variant}`, <Badge variant={variant}>Status</Badge>]);
}
fixtures.push(
  ['input-default', <Input label="Name" placeholder="Research" hint="Stored locally" />],
  ['input-error', <Input label="Name" value="?" readOnly error="Use a descriptive name" />],
  [
    'card-raised',
    <Card>
      <CardHeader>
        <CardTitle>Workspace</CardTitle>
      </CardHeader>
      <CardContent>Local-first content</CardContent>
    </Card>,
  ],
  ['skeleton-line', <Skeleton className="h-4 w-32" />],
  ['switch-off', <Switch checked={false} onCheckedChange={() => undefined} label="Offline" />],
  ['switch-on', <Switch checked onCheckedChange={() => undefined} label="Offline" />],
  [
    'tabs-underline',
    <Tabs
      label="Views"
      items={[
        { id: 'a', label: 'List', content: 'List content' },
        { id: 'b', label: 'Timeline', content: 'Timeline content' },
      ]}
    />,
  ],
  [
    'tabs-pill',
    <Tabs
      label="Settings"
      variant="pill"
      items={[
        { id: 'a', label: 'General', content: 'General content' },
        { id: 'b', label: 'Advanced', content: 'Advanced content' },
      ]}
    />,
  ],
  [
    'toast-success',
    <ToastViewport
      notices={[{ id: 'one', title: 'Saved', tone: 'success' }]}
      onDismiss={() => undefined}
      label="Notifications"
      dismissLabel="Dismiss"
      className="!static"
    />,
  ],
);

describe('Rooya component visual contracts', () => {
  it('commits exactly the top 30 primitive states', () => {
    expect(fixtures).toHaveLength(30);
  });

  for (const [name, fixture] of fixtures) {
    it(name, () => {
      const { container } = render(fixture);
      expect(container.firstElementChild).toMatchSnapshot();
    });
  }
});
