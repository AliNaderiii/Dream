import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoRemote } from '@/lib/bridge/echo-remotegw';
import RemoteRoute from '@/routes/remote';

describe('Remote route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoRemote();
  });

  it('shows the loopback URL and keeps the token out of the QR', async () => {
    const { container } = render(<RemoteRoute />);
    expect(await screen.findByRole('heading', { name: 'Remote' })).toBeInTheDocument();
    expect(await screen.findByText('http://127.0.0.1:8765/')).toBeInTheDocument();
    expect(screen.getByText('This token stays on this machine')).toBeInTheDocument();
    expect(screen.getByText('Query-string tokens are refused.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Issue a read token' }));
    expect(await screen.findByText(/drm_EXAMPLE_not_a_real_key/)).toBeInTheDocument();
    const report = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(report.violations).toEqual([]);
  });
});
