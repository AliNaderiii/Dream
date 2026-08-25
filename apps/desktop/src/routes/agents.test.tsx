import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoWorkspace } from '@/lib/bridge/echo-workspace';
import AgentsRoute from '@/routes/agents';

describe('Agents route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoWorkspace();
  });

  it('plans, continues, reports an honest goal, and stops with live state', async () => {
    const { container } = render(<AgentsRoute />);

    expect(await screen.findByRole('heading', { name: 'Agent modes' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Draft plan' }));
    expect(await screen.findByText('pending_approval')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findAllByText(/done/)).not.toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Start goal' }));
    expect(await screen.findAllByText(/could not meet/)).not.toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(screen.getAllByText(/live state/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: 'Parse references' }));
    expect(await screen.findByText(/sales.csv/)).toBeInTheDocument();

    const report = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(report.violations).toEqual([]);
  });
});
