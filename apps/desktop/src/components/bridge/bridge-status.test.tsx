import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { BridgeErrorToast, BridgeStatusIndicator } from '@/components/bridge/bridge-status';
import { getBridgeClient, resetBridgeClient } from '@/lib/bridge/client';
import { BridgeRpcError } from '@/lib/bridge/errors';

describe('BridgeStatusIndicator', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders the connected state with an Echo badge in tests', () => {
    render(<BridgeStatusIndicator />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Echo')).toBeInTheDocument();
  });

  it('is not interactive while connected', () => {
    render(<BridgeStatusIndicator />);
    expect(screen.getByRole('button', { name: /Bridge Connected/ })).toBeDisabled();
  });
});

describe('BridgeErrorToast', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders nothing when there is no error', () => {
    const { container } = render(<BridgeErrorToast />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the taxonomy code and message after a failing call', async () => {
    render(<BridgeErrorToast />); // mounts and subscribes to the singleton client
    await act(async () => {
      await expect(getBridgeClient().call('bogus.method')).rejects.toBeInstanceOf(BridgeRpcError);
    });
    // Label + numeric code from the taxonomy, plus the message.
    expect(await screen.findByText('Unknown method')).toBeInTheDocument();
    expect(screen.getByText(/-32601/)).toBeInTheDocument();
    expect(screen.getByText(/echo: unknown method bogus\.method/)).toBeInTheDocument();
  });

  it('can be dismissed', async () => {
    render(<BridgeErrorToast />);
    await act(async () => {
      await expect(getBridgeClient().call('bogus.method')).rejects.toBeInstanceOf(BridgeRpcError);
    });
    const dismiss = await screen.findByRole('button', { name: 'Dismiss error' });
    fireEvent.click(dismiss);
    expect(screen.queryByText('Unknown method')).not.toBeInTheDocument();
  });
});
