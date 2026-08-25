import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoWorkspace } from '@/lib/bridge/echo-workspace';
import WorkspaceRoute from '@/routes/workspace';

describe('Workspace route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoWorkspace();
  });

  it('shows in-place roots and a CSV chart preview with no axe violations', async () => {
    const { container } = render(<WorkspaceRoute />);

    expect(await screen.findByRole('heading', { name: 'Workspace' })).toBeInTheDocument();
    expect(await screen.findByText('In place — never copied')).toBeInTheDocument();
    expect(await screen.findByText('sales.csv')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'sales.csv' }));
    expect(await screen.findAllByText('North')).not.toHaveLength(0);
    expect(screen.getByText('not executed')).toBeInTheDocument();

    const report = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(report.violations).toEqual([]);
  });
});
