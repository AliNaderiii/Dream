import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoSpace } from '@/lib/bridge/echo-space';
import SpaceRoute from '@/routes/space';

describe('Space route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoSpace();
  });

  it('lists the seed space and keeps drafts pending until approve', async () => {
    const { container } = render(<SpaceRoute />);

    expect(await screen.findByRole('heading', { name: 'Space' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Create space' }));
    expect(await screen.findByRole('button', { name: 'Studio' })).toBeInTheDocument();
    expect(screen.getByLabelText('Instruction doc')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Rule'), { target: { value: 'every day at 9 AM' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }));
    expect(await screen.findByText('APPROVAL_PENDING')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('APPROVED')).toBeInTheDocument();

    const report = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(report.violations).toEqual([]);
  });
});
