import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoGws } from '@/lib/bridge/echo-gws';
import GoogleRoute from '@/routes/gws';

describe('Google route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoGws();
  });

  it('states read-only Gmail Calendar Drive', async () => {
    const { container } = render(<GoogleRoute />);
    expect(await screen.findByRole('heading', { name: 'Google' })).toBeInTheDocument();
    expect(await screen.findByText(/read-only Gmail, Calendar, and Drive/i)).toBeInTheDocument();
    const report = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(report.violations).toEqual([]);
  });
});
