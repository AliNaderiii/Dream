import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { useBridge } from '@/lib/bridge/hooks';

describe('useBridge', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('exposes a ready echo client in the test environment', () => {
    const { result } = renderHook(() => useBridge());
    expect(result.current.state).toBe('ready');
    expect(result.current.isFallback).toBe(true);
    expect(typeof result.current.call).toBe('function');
  });

  it('call performs a request/response round-trip', async () => {
    const { result } = renderHook(() => useBridge());
    let version: { protocol: string } | undefined;
    await act(async () => {
      version = await result.current.call<{ protocol: string }>('sidecar.version');
    });
    expect(version?.protocol).toBe('1.0');
  });

  it('stream invokes onChunk and resolves with the final reply', async () => {
    const { result } = renderHook(() => useBridge());
    const chunks: string[] = [];

    let session: { session_id: string } | undefined;
    await act(async () => {
      session = await result.current.call<{ session_id: string }>('session.create');
    });

    let reply = '';
    await act(async () => {
      reply = (
        await result.current.stream<{ reply: string }>(
          'conversation.send',
          { session_id: session!.session_id, message: 'hook test' },
          (c) => chunks.push(c.token),
        )
      ).reply;
    });

    expect(reply).toBe('Echo: hook test');
    expect(chunks.join('')).toBe('Echo: hook test');
  });

  it('reflects state transitions through the client event emitter', async () => {
    const { result } = renderHook(() => useBridge());
    expect(result.current.state).toBe('ready');

    act(() => {
      // reconnect() flips the client into 'reconnecting' and emits a state event.
      result.current.reconnect();
    });
    await waitFor(() => {
      expect(result.current.state).toBe('reconnecting');
    });
  });
});
