/**
 * Workbench render tests against the seeded echo transport: registry list,
 * preview grid (sort/filter/paginate/cell copy), profile cards, chart
 * suggestions, notebook view, and report preview with PDF download.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { resetBridgeClient, getBridgeClient } from '@/lib/bridge/client';
import { listDatasets } from '@/lib/bridge/data-science';
import { DataRoute } from '@/routes/data';
import { DataDatasetRoute } from '@/routes/data.dataset';

async function seededDatasetId(): Promise<string> {
  const { datasets } = await listDatasets(getBridgeClient());
  return datasets[0].dataset_id;
}

function renderWorkbench(datasetId: string) {
  return render(
    <MemoryRouter initialEntries={[`/data/${datasetId}`]}>
      <Routes>
        <Route path="/data" element={<DataRoute />} />
        <Route path="/data/:datasetId" element={<DataDatasetRoute />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DataRoute (registry)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('lists the seeded dataset with shape and format', async () => {
    render(
      <MemoryRouter initialEntries={['/data']}>
        <Routes>
          <Route path="/data" element={<DataRoute />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText('sales-2024')).toBeInTheDocument();
    expect(screen.getByText(/1,000 rows × 7 columns/)).toBeInTheDocument();
    expect(screen.getByText('csv')).toBeInTheDocument();
  });
});

describe('DataDatasetRoute (workbench)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders the preview grid and sorts by column', async () => {
    const user = userEvent.setup();
    renderWorkbench(await seededDatasetId());

    // Preview tab is default: table headers present.
    const grid = await screen.findByRole('table');
    expect(within(grid).getByText('region')).toBeInTheDocument();

    // Sort by quantity ascending: first data row shows the minimum (1).
    await user.click(screen.getByRole('button', { name: 'Sort by quantity' }));
    await waitFor(() => {
      const rows = within(grid).getAllByRole('row');
      expect(within(rows[1]).getAllByText('1').length).toBeGreaterThan(0);
    });
  });

  it('filters rows and paginates', async () => {
    const user = userEvent.setup();
    renderWorkbench(await seededDatasetId());
    await screen.findByRole('table');

    const search = screen.getByRole('searchbox', { name: /filter rows/i });
    await user.type(search, 'north');
    await waitFor(() => {
      expect(screen.getByText(/of 50 rows/)).toBeInTheDocument();
    });

    await user.clear(search);
    const next = screen.getByRole('button', { name: 'Next' });
    await user.click(next);
    expect(screen.getByText(/Page 2 of/)).toBeInTheDocument();
  });

  it('copies a cell value to the clipboard', async () => {
    renderWorkbench(await seededDatasetId());
    await screen.findByRole('table');

    // Define the spy after render, and click with fireEvent so user-event's
    // own clipboard stub never replaces it.
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    const copyButtons = screen.getAllByRole('button', { name: /^Copy / });
    fireEvent.click(copyButtons[0]);
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0][0]).toBeTruthy();
  });

  it('shows the profiling summary with per-column cards', async () => {
    const user = userEvent.setup();
    renderWorkbench(await seededDatasetId());
    await screen.findByRole('table');

    await user.click(screen.getByRole('tab', { name: /Profile/ }));
    expect(await screen.findByText('Rows')).toBeInTheDocument();
    expect(screen.getByText('1,000')).toBeInTheDocument();

    // Expand the price column card: numeric stats appear.
    await user.click(screen.getByRole('button', { name: /price/ }));
    expect(await screen.findByText('mean')).toBeInTheDocument();
  });

  it('lists chart suggestions and renders one into the gallery', async () => {
    const user = userEvent.setup();
    renderWorkbench(await seededDatasetId());
    await screen.findByRole('table');

    await user.click(screen.getByRole('tab', { name: /Charts/ }));
    const suggestion = await screen.findByRole('button', {
      name: /line: invoice_date × revenue/,
    });
    await user.click(suggestion);

    // The rendered chart lands in the gallery with its size breakdown.
    await waitFor(() => {
      expect(screen.getAllByText(/png: /).length).toBeGreaterThan(0);
    });
  });

  it('renders the seeded notebook with outputs and runs a cell', async () => {
    const user = userEvent.setup();
    renderWorkbench(await seededDatasetId());
    await screen.findByRole('table');

    await user.click(screen.getByRole('tab', { name: /Notebook/ }));
    expect(await screen.findByText(/Sales 2024 — exploration/)).toBeInTheDocument();
    expect(screen.getByText(/groupby\('region'\)/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open in JupyterLab' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Run cell 1' }));
    expect(await screen.findByText(/echo: executed cell 1/)).toBeInTheDocument();
  });

  it('shows the report preview, scrollable, with a PDF download link', async () => {
    const user = userEvent.setup();
    renderWorkbench(await seededDatasetId());
    await screen.findByRole('table');

    await user.click(screen.getByRole('tab', { name: /Report/ }));
    const article = await screen.findByRole('article', { name: 'Report preview' });
    expect(article).toHaveClass('overflow-y-auto');
    expect(
      within(article).getByRole('heading', { name: 'Sales 2024 Annual Review' }),
    ).toBeInTheDocument();
    expect(within(article).getByText(/Rows: 1000/)).toBeInTheDocument();

    const download = screen.getByRole('link', { name: 'Download PDF' });
    expect(download).toHaveAttribute('download', 'report.pdf');
  });

  it('regenerates the report through the bridge', async () => {
    const user = userEvent.setup();
    renderWorkbench(await seededDatasetId());
    await screen.findByRole('table');

    await user.click(screen.getByRole('tab', { name: /Report/ }));
    await screen.findByRole('article', { name: 'Report preview' });
    await user.click(screen.getByRole('button', { name: /Regenerate/ }));
    // The regenerated report carries the dataset name in its title.
    expect(await screen.findByRole('heading', { name: /sales-2024 — Report/ })).toBeInTheDocument();
  });
});
