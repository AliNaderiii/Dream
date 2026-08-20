import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BridgeStatusIndicator } from '@/components/bridge/bridge-status';
import type { BridgeConnectionState } from '@/lib/bridge/types';

// Force the status indicator into a specific state without standing up the real
// bridge client. The factory cannot see outer variables, so the desired state
// lives on a hoisted mutable ref.
const stateRef = vi.hoisted<{ state: BridgeConnectionState }>(() => ({ state: 'restarting' }));

vi.mock('@/lib/bridge/hooks', () => ({
  useBridge: () => ({
    state: stateRef.state,
    isFallback: false,
    reconnect: () => {},
    lastError: null,
    client: undefined,
    call: () => Promise.resolve(undefined),
    stream: () => Promise.resolve(undefined),
  }),
}));

describe('BridgeStatusIndicator — S13 regression (the `dot` crash)', () => {
  it('renders the "restarting" state without throwing', () => {
    stateRef.state = 'restarting';
    expect(() => render(<BridgeStatusIndicator />)).not.toThrow();
    expect(screen.getByText('Reconnecting')).toBeInTheDocument();
  });

  it('renders an unknown/malformed state without throwing (falls back to Disconnected)', () => {
    stateRef.state = 'definitely-not-a-real-state' as BridgeConnectionState;
    expect(() => render(<BridgeStatusIndicator />)).not.toThrow();
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
  });
});
