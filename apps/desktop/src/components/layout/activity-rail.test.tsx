import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { ActivityRail } from '@/components/layout/activity-rail';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useAppStore } from '@/stores/use-app-store';

function renderRail() {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <ActivityRail />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

const initial = useAppStore.getState();

describe('ActivityRail drawer', () => {
  beforeEach(() => {
    useAppStore.setState(initial, true);
    // The rail defaults to hover-peek, unpinned — visually identical to the
    // historical icon-only rail until the pointer enters it.
    useAppStore.setState({ railMode: 'hover', railPinned: false });
  });

  it('lists every P0 destination plus providers and settings', () => {
    renderRail();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(nav).toBeInTheDocument();

    // Collapsed: destinations are reachable by their aria-label (tooltips).
    for (const label of [
      'Dashboard',
      'Chat',
      'Projects',
      'Scheduler',
      'Memory',
      'Skills',
      'Subagents',
      'Data',
      'Connectivity',
      'Providers',
      'Settings',
    ]) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
  });

  it('is collapsed by default and peeks on hover, collapsing on leave', () => {
    renderRail();
    const nav = screen.getByRole('navigation', { name: 'Primary' });

    // Default (hover, unpinned): labels are hidden, rail reports collapsed.
    expect(screen.queryByText('Chat')).not.toBeInTheDocument();
    expect(nav).toHaveAttribute('aria-expanded', 'false');

    fireEvent.pointerEnter(nav);
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(nav).toHaveAttribute('aria-expanded', 'true');

    fireEvent.pointerLeave(nav);
    expect(screen.queryByText('Chat')).not.toBeInTheDocument();
    expect(nav).toHaveAttribute('aria-expanded', 'false');
  });

  it('collapsed mode never shows labels', () => {
    useAppStore.setState({ railMode: 'collapsed', railPinned: false });
    renderRail();
    const nav = screen.getByRole('navigation', { name: 'Primary' });

    expect(nav).toHaveAttribute('aria-expanded', 'false');
    fireEvent.pointerEnter(nav);
    expect(nav).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Chat')).not.toBeInTheDocument();
  });

  it('expanded mode shows icon + label with no tooltip-only labels', () => {
    useAppStore.setState({ railMode: 'expanded', railPinned: false });
    renderRail();
    const nav = screen.getByRole('navigation', { name: 'Primary' });

    expect(nav).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    // Expanded items keep a usable accessible name without relying on tooltips.
    expect(screen.getByRole('link', { name: 'Chat' })).toBeInTheDocument();
  });

  it('pin holds the rail open in hover mode; unpin restores peek', async () => {
    const user = userEvent.setup();
    useAppStore.setState({ railMode: 'hover', railPinned: false });
    renderRail();
    const nav = screen.getByRole('navigation', { name: 'Primary' });

    // Pin open (pinning from a resting rail arms hover + pin).
    await user.click(screen.getByRole('button', { name: 'Pin rail open' }));
    expect(useAppStore.getState().railPinned).toBe(true);
    expect(nav).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Chat')).toBeInTheDocument();

    // Leaving the rail must NOT collapse it while pinned.
    fireEvent.pointerLeave(nav);
    expect(nav).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Chat')).toBeInTheDocument();

    // Unpin: back to hover-peek — labels disappear once the pointer leaves.
    await user.click(screen.getByRole('button', { name: 'Unpin rail' }));
    expect(useAppStore.getState().railPinned).toBe(false);
    fireEvent.pointerLeave(nav);
    expect(nav).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Chat')).not.toBeInTheDocument();

    // And it peeks again on hover.
    fireEvent.pointerEnter(nav);
    expect(nav).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Chat')).toBeInTheDocument();
    fireEvent.pointerLeave(nav);
    expect(nav).toHaveAttribute('aria-expanded', 'false');
  });

  it('mode button cycles collapsed → hover → expanded and back', async () => {
    const user = userEvent.setup();
    renderRail();

    const modeButton = screen.getByRole('button', { name: 'Rail mode: hover to peek' });
    await user.click(modeButton);
    expect(useAppStore.getState().railMode).toBe('expanded');

    const expandedButton = screen.getByRole('button', { name: 'Rail mode: expanded' });
    await user.click(expandedButton);
    expect(useAppStore.getState().railMode).toBe('collapsed');

    await user.click(screen.getByRole('button', { name: 'Rail mode: collapsed' }));
    expect(useAppStore.getState().railMode).toBe('hover');
  });

  it('pinning from collapsed arms hover so the pin has an immediate effect', async () => {
    const user = userEvent.setup();
    useAppStore.setState({ railMode: 'collapsed', railPinned: false });
    renderRail();
    const nav = screen.getByRole('navigation', { name: 'Primary' });

    await user.click(screen.getByRole('button', { name: 'Pin rail open' }));
    expect(useAppStore.getState().railMode).toBe('hover');
    expect(useAppStore.getState().railPinned).toBe(true);
    expect(nav).toHaveAttribute('aria-expanded', 'true');
  });
});
