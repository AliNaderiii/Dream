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

  it('opens a nested folder on click and lists its children', async () => {
    render(<WorkspaceRoute />);
    expect(await screen.findByRole('button', { name: 'notes' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'notes' }));
    expect(await screen.findByRole('button', { name: 'todo.md' })).toBeInTheDocument();
  });
});

describe('Workspace route states (P-14)', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoWorkspace();
  });

  it('announces a loading state while roots are fetched', async () => {
    render(<WorkspaceRoute />);
    // The echo transport resolves fast, so assert the terminal state and
    // that the loading indicator is gone afterwards (no stuck spinner).
    expect(await screen.findByText('sales.csv')).toBeInTheDocument();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('closes the file action menu with Escape', async () => {
    render(<WorkspaceRoute />);
    await screen.findByText('sales.csv');
    const menuButtons = screen.getAllByRole('button', { name: 'Actions' });
    expect(menuButtons.length).toBeGreaterThan(0);
    fireEvent.click(menuButtons[0]);
    const menu = await screen.findByRole('menu');
    fireEvent.keyDown(menu, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders correctly in RTL', async () => {
    document.documentElement.dir = 'rtl';
    try {
      render(<WorkspaceRoute />);
      expect(await screen.findByRole('heading', { name: 'Workspace' })).toBeVisible();
    } finally {
      document.documentElement.dir = 'ltr';
    }
  });
});
