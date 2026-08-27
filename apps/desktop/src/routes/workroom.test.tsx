import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoWorkroom } from '@/lib/bridge/echo-workroom';
import WorkroomRoute from '@/routes/workroom';

describe('Workroom route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoWorkroom();
  });

  it('states company mode, no send, and YOLO off', async () => {
    const { container } = render(<WorkroomRoute />);
    expect(await screen.findByRole('heading', { name: 'Workroom' })).toBeInTheDocument();
    expect(screen.getAllByText(/YOLO is off/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Chrome profile/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/never send/i).length).toBeGreaterThan(0);
    const report = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(report.violations).toEqual([]);
  });
});
