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
});
