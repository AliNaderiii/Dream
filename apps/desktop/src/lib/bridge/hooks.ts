/**
 * React bindings for the Dream bridge.
 *
 * `useBridge()` exposes a stable `BridgeClient`, a reactive connection state,
 * the last error, and bound `call`/`stream` helpers. It also runs a conservative
 * client-side auto-reconnect with exponential backoff for the rare case the
 * Rust supervisor reports `disconnected` and a nudge is needed.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { BridgeClient } from './client';
import { getBridgeClient, resetBridgeClient, type BridgeClientEvent } from './client';
import type { BridgeRpcError } from './errors';
import type { BridgeConnectionState, RpcParams, StreamChunk } from './types';

export interface UseBridgeResult {
  client: BridgeClient;
  state: BridgeConnectionState;
  lastError: BridgeRpcError | null;
  /** True when running on the in-memory echo fallback (no sidecar). */
  isFallback: boolean;
  /** Typed request/response. */
  call: <T>(method: string, params?: RpcParams) => Promise<T>;
  /** Streaming request with a per-chunk callback. */
  stream: <T>(
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ) => Promise<T>;
  /** Force a reconnect/restart of the sidecar. */
  reconnect: () => void;
}

/** Initial backoff (ms) for client-side reconnect; doubles up to the cap. */
const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

/**
 * The bridge hook. Mount once near the app root and read from descendants, or
 * call directly — it always returns the process-wide singleton client.
 */
export function useBridge(): UseBridgeResult {
  const client = useMemo(() => getBridgeClient(), []);
  const [state, setState] = useState<BridgeConnectionState>(client.state);
  const [lastError, setLastError] = useState<BridgeRpcError | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Subscribe to client events. The initial state already comes from
  // `useState(client.state)`, so this effect only reacts to later transitions.
  useEffect(() => {
    const off = client.on((event: BridgeClientEvent) => {
      if (event.type === 'state') setState(event.state);
      if (event.type === 'error') setLastError(event.error);
    });
    return off;
  }, [client]);

  // Client-side auto-reconnect with exponential backoff. The Rust supervisor
  // restarts the process on its own; this only nudges if it reports a lingering
  // disconnect, and resets the backoff once connected.
  useEffect(() => {
    if (client.transportKind !== 'tauri') return; // echo transport never needs this
    if (state === 'ready' || state === 'connecting' || state === 'reconnecting') {
      backoffRef.current = INITIAL_BACKOFF_MS;
      return;
    }
    // state === 'disconnected'
    const delay = backoffRef.current;
    backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
    reconnectTimer.current = setTimeout(() => client.reconnect(), delay);
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [state, client]);

  useEffect(() => {
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      // Reset the singleton between tests so each test gets a fresh client.
      if (import.meta.env?.MODE === 'test') resetBridgeClient();
    };
  }, []);

  const call = useCallback(
    <T>(method: string, params?: RpcParams) => client.call<T>(method, params ?? {}),
    [client],
  );
  const stream = useCallback(
    <T>(method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) =>
      client.stream<T>(method, params, { onChunk }),
    [client],
  );
  const reconnect = useCallback(() => client.reconnect(), [client]);

  return {
    client,
    state,
    lastError,
    isFallback: client.isFallback,
    call,
    stream,
    reconnect,
  };
}
