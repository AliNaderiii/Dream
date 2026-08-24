/**
 * SEC Stage B desktop surface — the persistent off-mode indicators.
 *
 * Pins: the banner and the status-bar chip render ONLY while the engine
 * reports approvals off; both stay hidden on the safe defaults, on bridge
 * errors, and while the bridge is not ready (a missing answer must never
 * look like "approvals are on").
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SecurityOffBanner } from '@/components/security/security-off-banner';
import { SecurityStatusIndicator } from '@/components/security/security-status-indicator';
import type { SecurityStatus } from '@/lib/bridge/security';

const MANUAL_STATUS: SecurityStatus = {
  mode: 'manual',
  cron_mode: 'deny',
  single_query_mode: 'deny',
  off_active: false,
  floor: 'always-on',
  history_path: null,
  history_available: true,
};

const OFF_STATUS: SecurityStatus = { ...MANUAL_STATUS, mode: 'off', off_active: true };

// The factory cannot see outer variables, so the fake bridge lives on a
// hoisted mutable ref (the established pattern for bridge mocks).
interface FakeBridge {
  state: 'ready' | 'connecting';
  call: (method: string) => Promise<SecurityStatus>;
}
const bridgeRef = vi.hoisted((): FakeBridge => ({
  state: 'ready',
  call: () => Promise.resolve(MANUAL_STATUS),
}));

vi.mock('@/lib/bridge/hooks', () => ({
  useBridge: () => ({
    state: bridgeRef.state,
    isFallback: true,
    reconnect: () => {},
    lastError: null,
    client: undefined,
    call: bridgeRef.call,
    stream: () => Promise.resolve(undefined),
  }),
}));

function setBridge(next: Partial<typeof bridgeRef>): void {
  bridgeRef.state = next.state ?? 'ready';
  bridgeRef.call = next.call ?? (() => Promise.resolve(MANUAL_STATUS));
}

describe('SecurityOffBanner', () => {
  it('stays hidden while approvals work normally (manual mode)', async () => {
    setBridge({ call: () => Promise.resolve(MANUAL_STATUS) });
    const { container } = render(<SecurityOffBanner />);
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('renders a persistent alert while approvals are off', async () => {
    setBridge({ call: () => Promise.resolve(OFF_STATUS) });
    render(<SecurityOffBanner />);
    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(screen.getByText('Approval engine is OFF')).toBeInTheDocument();
    // The banner names the one control that still holds: the floor.
    expect(alert.textContent).toContain('security floor');
  });

  it('stays hidden when the security call fails (fail-safe, not fail-confident)', async () => {
    setBridge({ call: () => Promise.reject(new Error('boom')) });
    const { container } = render(<SecurityOffBanner />);
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('does not even ask while the bridge is not ready', async () => {
    const call = vi.fn(() => Promise.resolve(OFF_STATUS));
    setBridge({ state: 'connecting', call });
    const { container } = render(<SecurityOffBanner />);
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(call).not.toHaveBeenCalled();
  });
});

describe('SecurityStatusIndicator', () => {
  it('renders nothing while approvals work normally', async () => {
    setBridge({ call: () => Promise.resolve(MANUAL_STATUS) });
    const { container } = render(<SecurityStatusIndicator />);
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('shows the labelled chip while approvals are off', async () => {
    setBridge({ call: () => Promise.resolve(OFF_STATUS) });
    render(<SecurityStatusIndicator />);
    expect(await screen.findByLabelText('Approvals off')).toBeInTheDocument();
    expect(screen.getByText('Approvals off')).toBeInTheDocument();
  });
});
