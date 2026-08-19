import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { DashboardRoute } from '@/routes/dashboard';

describe('DashboardRoute (S05 first-run)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('offers the offline-first story: echo works, Ollama offered, BYOK optional', async () => {
    render(
      <MemoryRouter>
        <DashboardRoute />
      </MemoryRouter>,
    );

    // Echo works offline — no account needed.
    expect(await screen.findByText('Works offline — no account needed')).toBeInTheDocument();
    expect(
      screen.getByText('Offline echo engine — no network or account required'),
    ).toBeInTheDocument();

    // Ollama is offered as the local upgrade.
    expect(screen.getByText('Add a local model with Ollama')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set up Ollama' })).toBeInTheDocument();

    // BYOK is optional and clearly labelled as leaving the machine.
    expect(screen.getByText('Bring your own API key')).toBeInTheDocument();
    expect(
      screen.getByText('Optional — your prompts then leave this machine to that provider.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add a provider key' })).toBeInTheDocument();
  });

  it('shows the resolved route and the data-leaves sentence from the echo fallback', async () => {
    render(
      <MemoryRouter>
        <DashboardRoute />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Current route/)).toBeInTheDocument();
    // Echo fallback: nothing leaves the machine.
    expect(screen.getByText('Prompts never leave this machine')).toBeInTheDocument();
    expect(
      screen.getByText('Route: echo — fully offline echo backend; no data leaves this machine.'),
    ).toBeInTheDocument();
    // The opposite sentence must never appear in echo mode.
    expect(screen.queryByText('Prompts leave this machine')).not.toBeInTheDocument();
  });
});
