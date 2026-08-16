import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { ConnectivityRoute } from '@/routes/connectivity';
import { useConnectivityStore } from '@/stores/use-connectivity-store';

describe('ConnectivityRoute', () => {
  beforeEach(() => {
    resetBridgeClient();
    useConnectivityStore.setState({
      platforms: [],
      status: null,
      logs: null,
      linkCodes: {},
      expandedPlatform: null,
      loading: false,
      error: null,
    });
  });

  it('renders all six platform cards with the seeded log', async () => {
    render(<ConnectivityRoute />);
    await screen.findByText(/Talk to Dream from Telegram/);
    for (const label of ['Telegram', 'Discord', 'Slack', 'WhatsApp', 'Signal', 'Email']) {
      expect(screen.getByRole('heading', { name: label })).toBeInTheDocument();
    }
    // Seeded message-log rows render.
    await waitFor(() => {
      expect(screen.getByText(/Reminder set for 18:00/)).toBeInTheDocument();
    });
  });

  it('starts the gateway from the header button', async () => {
    const user = userEvent.setup();
    render(<ConnectivityRoute />);
    await screen.findByText(/Talk to Dream from Telegram/);
    await user.click(screen.getByRole('button', { name: 'Start' }));
    await waitFor(() => {
      expect(screen.getByText('Gateway running')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
  });

  it('toggles a platform on and opens its configure form', async () => {
    const user = userEvent.setup();
    render(<ConnectivityRoute />);
    await screen.findByText(/Talk to Dream from Telegram/);

    const card = screen.getByTestId('platform-card-telegram');

    await user.click(within(card).getByRole('switch', { name: /Telegram enabled/ }));
    await waitFor(() => {
      expect(within(card).getByText('Needs config')).toBeInTheDocument();
    });

    await user.click(within(card).getByRole('button', { name: 'Configure' }));
    const form = await screen.findByRole('form', { name: 'Telegram configuration' });
    const tokenInput = within(form).getByLabelText(/Bot token/);
    expect(tokenInput).toHaveAttribute('type', 'password');
    await user.type(tokenInput, '123456:ABCDEF');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(within(card).queryByText('Needs config')).not.toBeInTheDocument();
    });
    // The secret never round-trips into the UI: the catalog carries no
    // config values, and the badge reflects the sidecar's redacted reply.
    const telegram = useConnectivityStore
      .getState()
      .platforms.find((platform) => platform.name === 'telegram');
    expect(telegram?.configured).toBe(true);
    expect(JSON.stringify(useConnectivityStore.getState().platforms)).not.toContain(
      '123456:ABCDEF',
    );
  });

  it('reveals a secret field only while the eye toggle is pressed', async () => {
    const user = userEvent.setup();
    render(<ConnectivityRoute />);
    await screen.findByText(/Talk to Dream from Telegram/);
    const telegramCard = screen.getByTestId('platform-card-telegram');
    await user.click(within(telegramCard).getByRole('button', { name: 'Configure' }));
    const form = await screen.findByRole('form', { name: 'Telegram configuration' });
    const tokenInput = within(form).getByLabelText(/Bot token/);
    await user.type(tokenInput, 'secret-token');
    expect(tokenInput).toHaveAttribute('type', 'password');
    await user.click(within(form).getByRole('button', { name: 'Reveal secret' }));
    expect(tokenInput).toHaveAttribute('type', 'text');
    await user.click(within(form).getByRole('button', { name: 'Hide secret' }));
    expect(tokenInput).toHaveAttribute('type', 'password');
  });

  it('explains that Signal log content is never stored', async () => {
    const user = userEvent.setup();
    render(<ConnectivityRoute />);
    await screen.findByText(/Talk to Dream from Telegram/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Platform' }), 'signal');
    await waitFor(() => {
      expect(
        screen.getByText(/end-to-end encrypted — the log records only that a message happened/),
      ).toBeInTheDocument();
    });
  });
});
