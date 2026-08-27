import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoBrowse } from '@/lib/bridge/echo-browse';
import BrowseRoute from '@/routes/browse';

describe('Browse route', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoBrowse();
  });

  it('states allow once, no YOLO, and no Chrome profile', async () => {
    const { container } = render(<BrowseRoute />);
    expect(await screen.findByRole('heading', { name: 'Browse' })).toBeInTheDocument();
    expect(screen.getAllByText(/Allow once/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/YOLO is off/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Chrome profile/i).length).toBeGreaterThan(0);
    const report = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(report.violations).toEqual([]);
  });
});
