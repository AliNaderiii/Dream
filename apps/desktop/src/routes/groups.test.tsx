import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoBots } from '@/lib/bridge/echo-bots';
import { resetEchoGroups } from '@/lib/bridge/echo-groups';
import GroupsRoute from '@/routes/groups';

describe('Groups route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoBots();
    resetEchoGroups();
  });

  it('states the three-round cap and that YOLO is off', async () => {
    const { container } = render(<GroupsRoute />);
    expect(await screen.findByRole('heading', { name: 'Group' })).toBeInTheDocument();
    expect(await screen.findByText(/3 rounds/i)).toBeInTheDocument();
    expect(screen.getByText(/YOLO is off/i)).toBeInTheDocument();
    const report = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(report.violations).toEqual([]);
  });
});
