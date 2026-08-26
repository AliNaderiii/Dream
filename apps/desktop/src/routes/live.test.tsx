import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoLiveloop } from '@/lib/bridge/echo-liveloop';
import LiveRoute from '@/routes/live';

describe('Live route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoLiveloop();
  });

  it('states the status-bar honesty rule', async () => {
    const { container } = render(<LiveRoute />);
    expect(await screen.findByRole('heading', { name: 'Live' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Route honesty' })).toBeInTheDocument();
    expect(
      await screen.findByText(/Earth Runtime while this bar still says Echo/i),
    ).toBeInTheDocument();
    expect(await screen.findByText(/this bar is not the pane/i)).toBeInTheDocument();
    const report = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(report.violations).toEqual([]);
  });
});
