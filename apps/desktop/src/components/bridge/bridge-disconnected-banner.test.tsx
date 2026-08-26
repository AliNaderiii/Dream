import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { BridgeDisconnectedBanner } from '@/components/bridge/bridge-disconnected-banner';
import {
  EchoBridgeTransport,
  getBridgeClient,
  resetBridgeClient,
  type BridgeTransport,
} from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

class DisconnectedTransport implements BridgeTransport {
  readonly kind = 'tauri' as const;
  private readonly echo = new EchoBridgeTransport();
  private handlers = new Set<(state: BridgeConnectionState) => void>();

  request<T>(id: RpcId, method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) {
    return this.echo.request<T>(id, method, params, onChunk);
  }

  onState(handler: (state: BridgeConnectionState) => void) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  reconnect() {}

  emit(state: BridgeConnectionState) {
    this.handlers.forEach((handler) => handler(state));
  }
}

describe('BridgeDisconnectedBanner containment', () => {
  beforeEach(() => resetBridgeClient());

  it('keeps the action on the end edge, text in its own shrinking column', () => {
    const transport = new DisconnectedTransport();
    getBridgeClient().setTransport(transport);
    render(<BridgeDisconnectedBanner />);

    act(() => transport.emit('disconnected'));

    const banner = screen.getByRole('status');
    // Text column: shrinkable, wraps inside its own box (never under the
    // action button); action: pinned to the inline-end edge, never overlapped.
    const textColumn = banner.querySelector('.bridge-banner-text');
    const action = banner.querySelector('.bridge-banner-action');
    expect(textColumn).not.toBeNull();
    expect(action).not.toBeNull();
    expect(action!.textContent).toBe('Try again');
    // The retry button must be a direct flex child on the end edge, not nested
    // inside the text column.
    expect(banner.lastElementChild).toBe(action);
    expect(banner.contains(textColumn)).toBe(true);
  });
});
