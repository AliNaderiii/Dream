import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { BridgeOfflineBanner } from '@/components/shared/bridge-offline-banner';
import {
  EchoBridgeTransport,
  getBridgeClient,
  resetBridgeClient,
  type BridgeTransport,
} from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

class OfflineTransport implements BridgeTransport {
  readonly kind = 'tauri' as const;
  reconnects = 0;
  private readonly echo = new EchoBridgeTransport();
  private handlers = new Set<(state: BridgeConnectionState) => void>();

  request<T>(id: RpcId, method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) {
    return this.echo.request<T>(id, method, params, onChunk);
  }

  onState(handler: (state: BridgeConnectionState) => void) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  reconnect() {
    this.reconnects += 1;
  }

  emit(state: BridgeConnectionState) {
    this.handlers.forEach((handler) => handler(state));
  }
}

describe('BridgeOfflineBanner', () => {
  beforeEach(() => resetBridgeClient());

  it('shows an actionable bridge-dead state and invokes reconnect', async () => {
    const user = userEvent.setup();
    const transport = new OfflineTransport();
    getBridgeClient().setTransport(transport);
    render(<BridgeOfflineBanner />);

    act(() => transport.emit('disconnected'));
    expect(screen.getByRole('status')).toHaveTextContent('The Dream engine is offline');
    await user.click(screen.getByRole('button', { name: 'Reconnect' }));
    expect(transport.reconnects).toBe(1);
  });
});
