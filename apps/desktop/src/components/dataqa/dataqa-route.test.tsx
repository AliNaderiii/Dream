import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import DataQaRoute from '@/routes/dataqa';

describe('Data Q&A route', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('discovers Echo data and returns grounded evidence with a validated chart', async () => {
    const { container } = render(<DataQaRoute />);

    expect(await screen.findByText('Sales 2024')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Use dataset' }));
    expect(await screen.findByText(/1,000 rows · 6 columns/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText(/^Average revenue by region —/)).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('validated')).toBeInTheDocument();
    expect(screen.getByText('Generated code and audit trail')).toBeInTheDocument();

    const report = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(report.violations).toEqual([]);
  });
});
