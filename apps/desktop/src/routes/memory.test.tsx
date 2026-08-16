import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { MemoryRoute } from '@/routes/memory';

describe('MemoryRoute', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders the seeded memories with count badges', async () => {
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    const semanticTab = screen.getByRole('tab', { name: /Semantic/ });
    expect(within(semanticTab).getByText('4')).toBeInTheDocument();
  });

  it('filters the list by kind', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    await user.click(screen.getByRole('tab', { name: /Procedural/ }));

    await waitFor(() => {
      expect(screen.queryByText(/Dream stores memories as semantic/)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/To export a skill/)).toBeInTheDocument();
  });

  it('debounces the search box before querying', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    await user.type(screen.getByRole('searchbox', { name: /search memories/i }), 'skills');

    // The unrelated row survives only until the debounced query lands.
    await waitFor(
      () => {
        expect(screen.queryByText(/Dream stores memories as semantic/)).not.toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    expect(screen.getByText(/Paired on the skills import validation/)).toBeInTheDocument();
  });

  it('opens the detail drawer for a memory', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    const card = await screen.findByText(/Dream stores memories as semantic/);

    await user.click(card);

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('Memory detail')).toBeInTheDocument();
    expect(within(drawer).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('switches to the timeline view and keeps the filters', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    await user.click(screen.getByRole('tab', { name: /Episodic/ }));
    await waitFor(() => {
      expect(screen.queryByText(/Dream stores memories as semantic/)).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Timeline/ }));

    expect(screen.getByRole('group', { name: 'Timeline zoom' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Episodic/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText(/Reviewed the P-05 memory explorer/)).toBeInTheDocument();
  });
});
