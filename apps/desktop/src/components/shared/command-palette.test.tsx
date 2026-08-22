import axe from 'axe-core';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CommandPalette } from '@/components/shared/command-palette';
import type { CommandItem } from '@/hooks/use-keyboard-shortcuts';
import { useAppStore } from '@/stores/use-app-store';

function fixture(run = vi.fn()): CommandItem[] {
  return [
    { id: 'new', description: 'New session', category: 'Actions', keys: ['Ctrl', 'N'], run },
    { id: 'settings', description: 'Open Settings', category: 'Navigation', run },
    { id: 'memory', description: 'بازکردن حافظه', category: 'پیمایش', run },
  ];
}

beforeEach(() => {
  useAppStore.setState({ commandPaletteOpen: true });
});

afterEach(() => {
  document.documentElement.dir = 'ltr';
  useAppStore.setState({ commandPaletteOpen: false });
});

describe('CommandPalette', () => {
  it('groups commands and exposes combobox/listbox semantics', () => {
    render(<CommandPalette commands={fixture()} />);
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Search commands' })).toHaveAttribute(
      'aria-controls',
      'dream-command-results',
    );
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(3);
  });

  it('filters with fuzzy Persian search and runs the selected command', async () => {
    const user = userEvent.setup();
    const run = vi.fn();
    render(<CommandPalette commands={fixture(run)} />);
    await user.type(screen.getByRole('combobox'), 'حافظه');
    expect(screen.getByRole('option', { name: 'بازکردن حافظه' })).toBeInTheDocument();
    await user.keyboard('{Enter}');
    expect(run).toHaveBeenCalledTimes(1);
  });

  it('supports arrows, Home, End, and Enter from the focused input', () => {
    const run = vi.fn();
    render(<CommandPalette commands={fixture(run)} />);
    const input = screen.getByRole('combobox');
    input.focus();
    fireEvent.keyDown(input, { key: 'End' });
    expect(input).toHaveAttribute('aria-activedescendant', 'dream-command-2');
    fireEvent.keyDown(input, { key: 'Home' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(run).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().commandPaletteOpen).toBe(false);
  });

  it('completes the keyboard-only type, arrow, enter, reopen, and Escape walkthrough', async () => {
    const user = userEvent.setup();
    const run = vi.fn();
    render(<CommandPalette commands={fixture(run)} />);
    const input = screen.getByRole('combobox');
    await user.type(input, 'session');
    await user.keyboard('{ArrowDown}{Enter}');
    expect(run).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().commandPaletteOpen).toBe(false);

    act(() => useAppStore.getState().setCommandPaletteOpen(true));
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveFocus());
    await user.keyboard('{Escape}');
    expect(useAppStore.getState().commandPaletteOpen).toBe(false);
  });

  it('announces an empty result set', async () => {
    const user = userEvent.setup();
    render(<CommandPalette commands={fixture()} />);
    await user.type(screen.getByRole('combobox'), 'no command matches this');
    expect(screen.getByRole('status')).toHaveTextContent('No matching commands');
  });

  it('has no detectable accessibility violations in RTL', async () => {
    document.documentElement.dir = 'rtl';
    render(<CommandPalette commands={fixture()} />);
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveFocus());
    const dialog = screen.getByRole('dialog', { name: 'Command palette' });
    const result = await axe.run(dialog, { rules: { 'color-contrast': { enabled: false } } });
    expect(result.violations).toEqual([]);
    expect(within(dialog).getByRole('listbox')).toBeInTheDocument();
  });
});
