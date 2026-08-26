import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { SettingsRoute } from '@/routes/settings';

describe('SettingsRoute (S05 billing)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('shows the plan & usage section on the general tab', async () => {
    render(<SettingsRoute />);

    expect(screen.getByRole('heading', { name: 'Settings & Integrations' })).toBeInTheDocument();

    // The billing section header and its honest content (echo fallback).
    expect(await screen.findByText('Plan & usage')).toBeInTheDocument();
    expect(screen.getByText('محلی')).toBeInTheDocument();
    expect(screen.getByText('(Local)')).toBeInTheDocument();
    expect(screen.getByText('Unlimited turns')).toBeInTheDocument();
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('Offline echo')).toBeInTheDocument();
    expect(screen.getByText('Prompts never leave this machine')).toBeInTheDocument();

    // The price must never be a made-up number.
    expect(screen.queryByText(/IRR|تومان|rial/i)).not.toBeInTheDocument();

    // Disabled upgrade affordance — no checkout, no Zarinpal.
    expect(screen.getByRole('button', { name: 'Upgrade (coming)' })).toBeDisabled();
  });

  it('keeps the existing general-tab sections intact', async () => {
    render(<SettingsRoute />);

    expect(await screen.findByText('Appearance')).toBeInTheDocument();
    expect(screen.getByText('Window')).toBeInTheDocument();
    expect(screen.getByText('Workspace')).toBeInTheDocument();
    // Language picker still offers Persian.
    expect(screen.getByRole('button', { name: /🇮🇷/ })).toBeInTheDocument();
  });

  it('contains the language row: description and locale chips never share a line box', async () => {
    render(<SettingsRoute />);

    // The row's description text ("Persian switches the whole shell to
    // right-to-left.") and the locale chips must live in separate flex
    // children so chips wrap inside their own area — never through the
    // description (owner screenshot: English description running through the
    // locale chips).
    const description = await screen.findByText(
      'Persian switches the whole shell to right-to-left.',
    );
    const labelColumn = description.parentElement;
    expect(labelColumn).not.toBeNull();
    expect(labelColumn!.className).toContain('min-w-0');

    const chips = screen.getAllByRole('button', { name: /🇮🇷|🇬🇧|🇩🇪|🇪🇸|🇫🇷|🇯🇵|🇰🇷|🇨🇳/ });
    expect(chips.length).toBeGreaterThanOrEqual(8);
    // All eight locale chips share one wrapping chip row (their own row with
    // gap — the fix for chips wrapping through the next control).
    const chipBoxes = new Set(chips.map((chip) => chip.parentElement));
    expect(chipBoxes.size).toBe(1);
    const chipRow = [...chipBoxes][0]!;
    expect(chipRow.className).toContain('flex-wrap');
    expect(chipRow.className).toContain('gap-1');

    // The control column around the chip row: can shrink, wraps inside its own
    // box, capped at its own column on wide rows — never overlapping the label.
    const controlColumn = chipRow.parentElement;
    expect(controlColumn).not.toBeNull();
    expect(controlColumn!.className).toContain('min-w-0');
    expect(controlColumn!.className).toContain('flex-wrap');
    expect(controlColumn!.className).toContain('md:max-w-[55%]');

    // The control column is a sibling of the label column inside the row, not
    // a descendant — no text runs through the chips.
    expect(controlColumn).toBe(labelColumn!.parentElement!.lastElementChild);
    expect(labelColumn!.parentElement!.className).toContain('md:flex-row');
    expect(labelColumn!.parentElement!.className).toContain('flex-col');
  });
});
