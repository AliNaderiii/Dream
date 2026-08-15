/**
 * The Dream bridge RPC client.
 *
 * `BridgeClient` speaks JSON-RPC 2.0 to the Python sidecar through a
 * `BridgeTransport`. Two transports ship:
 *
 * - `TauriBridgeTransport` — the real path: the Rust supervisor exposes a
 *   `bridge_send(id, method, params)` command and emits `bridge://chunk` /
 *   `bridge://state` events. Used under Tauri.
 * - `EchoBridgeTransport` — an in-memory fallback so the UI works in `npm run
 *   dev` and unit tests with no sidecar running.
 *
 * The client generates request ids, routes stream chunks by id, tracks
 * connection state, and re-emits everything through a tiny event emitter so
 * React hooks (`useBridge`) can subscribe.
 */

import { invoke as tauriInvoke } from '@tauri-apps/api/core';

import { listen } from '@/lib/tauri';
import { isTauri } from '@/utils/platform';

import { BridgeRpcError, toBridgeError } from './errors';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from './types';

/** Events the client re-emits for hooks/components. */
export type BridgeClientEvent =
  | { type: 'state'; state: BridgeConnectionState }
  | { type: 'error'; error: BridgeRpcError }
  | { type: 'chunk'; chunk: StreamChunk };

type EventHandler = (event: BridgeClientEvent) => void;

/** Callbacks for an in-flight streaming request. */
export interface StreamHandlers {
  onChunk?: (chunk: StreamChunk) => void;
}

/**
 * A transport carries one request at a time and reports state changes.
 * Implementations: `TauriBridgeTransport` (sidecar) and `EchoBridgeTransport`
 * (browser fallback).
 */
export interface BridgeTransport {
  readonly kind: 'tauri' | 'echo';
  /** Execute one request; for streaming methods, `onChunk` fires per chunk. */
  request<T>(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T>;
  /** Subscribe to connection-state transitions. Returns an unsubscribe. */
  onState(handler: (state: BridgeConnectionState) => void): () => void;
  /** Ask the supervisor to reconnect/restart the sidecar (no-op for echo). */
  reconnect(): void;
}

// --------------------------------------------------------------------------- //
// Tauri transport — talks to the Rust bridge supervisor.
// --------------------------------------------------------------------------- //

const CHUNK_EVENT = 'bridge://chunk';
const STATE_EVENT = 'bridge://state';

export class TauriBridgeTransport implements BridgeTransport {
  readonly kind = 'tauri' as const;
  private stateHandlers = new Set<(s: BridgeConnectionState) => void>();

  constructor() {
    void this.wireState();
  }

  private async wireState(): Promise<void> {
    // The listener lives for the app lifetime; Tauri dedupes on window close.
    await listen<{ state: BridgeConnectionState }>(STATE_EVENT, (payload) => {
      for (const handler of this.stateHandlers) handler(payload.state);
    });
  }

  onState(handler: (state: BridgeConnectionState) => void): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  reconnect(): void {
    void tauriInvoke('bridge_restart').catch(() => {
      /* supervisor may be mid-restart; ignore */
    });
  }

  async request<T>(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    let unlisten: (() => void) | undefined;
    if (onChunk) {
      // Route only the chunks whose id matches this request.
      unlisten = await listen<StreamChunk>(CHUNK_EVENT, (chunk) => {
        if (chunk.id === id) onChunk(chunk);
      });
    }
    try {
      // The Rust command returns the JSON-RPC `result` value, or throws a
      // structured {code, message, data?} error serialised by Tauri.
      return await tauriInvoke<T>('bridge_send', { id, method, params });
    } catch (err) {
      throw toBridgeError(err);
    } finally {
      unlisten?.();
    }
  }
}

// --------------------------------------------------------------------------- //
// Echo transport — browser/test fallback (no sidecar).
// --------------------------------------------------------------------------- //

/** Splits text into token-sized fragments, mirroring `dream.bridge.tokenise`. */
export function tokenise(text: string, maxChars = 12): string[] {
  if (!text) return [];
  const parts = text.match(/\S+\s*|\s+/g) ?? [text];
  const out: string[] = [];
  for (const word of parts) {
    if (word.length <= maxChars) out.push(word);
    else for (let i = 0; i < word.length; i += maxChars) out.push(word.slice(i, i + maxChars));
  }
  return out;
}

interface EchoSession {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  provider: string;
}

let echoCounter = 0;

/**
 * An in-memory transport that answers a useful subset of methods locally, so
 * the conversation UI is exercisable in a browser without the Python sidecar.
 * It is intentionally minimal and deterministic.
 */
export class EchoBridgeTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private sessions = new Map<string, EchoSession>();
  private stateHandlers = new Set<(s: BridgeConnectionState) => void>();
  private startedAt = Date.now();

  onState(handler: (state: BridgeConnectionState) => void): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  reconnect(): void {
    /* no-op: the echo transport is always ready. */
  }

  async request<T>(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    // Yield once so callers observing async ordering in tests stay deterministic.
    await Promise.resolve();
    return this.handle(id, method, params, onChunk) as Promise<T>;
  }

  private async handle(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<unknown> {
    switch (method) {
      case 'session.create': {
        const sid = `echo-${++echoCounter}`;
        const now = Date.now();
        this.sessions.set(sid, {
          id: sid,
          title: (params['title'] as string) || 'New session',
          created_at: now,
          updated_at: now,
          message_count: 0,
          provider: 'echo',
        });
        return { session_id: sid, id: sid, title: this.sessions.get(sid)!.title, created_at: now };
      }
      case 'session.list':
        return {
          sessions: [...this.sessions.values()].sort((a, b) => b.updated_at - a.updated_at),
        };
      case 'session.get':
        return this.sessions.get(params['session_id'] as string) ?? null;
      case 'session.delete':
        this.sessions.delete(params['session_id'] as string);
        return { deleted: true };
      case 'session.rename': {
        const s = this.sessions.get(params['session_id'] as string);
        if (s) {
          s.title = (params['title'] as string) || s.title;
          s.updated_at = Date.now();
        }
        return s ?? null;
      }
      case 'conversation.send': {
        const message = (params['message'] as string) ?? '';
        const reply = `Echo: ${message}`;
        for (const token of tokenise(reply)) {
          onChunk?.({ id, token });
          await Promise.resolve();
        }
        const s = this.sessions.get(params['session_id'] as string);
        if (s) {
          s.message_count += 1;
          s.updated_at = Date.now();
        }
        return {
          reply,
          tool_calls: [],
          memories_used: [],
          memories_injected_ids: [],
          memories_created: [],
          memories_superseded: [],
          memories_merged: [],
          elapsed_seconds: 0,
          extraction: { status: 'disabled', facts: [], raw_text: '' },
          memory_errors: [],
        };
      }
      case 'conversation.stop':
        return { stopped: true };
      case 'provider.list':
        return {
          providers: [
            { id: 'echo', kind: 'echo', label: 'Echo', local: true, status: 'connected' },
          ],
          default: 'echo',
        };
      case 'provider.test':
        return { ok: true, provider: params['provider'] ?? 'echo', latency_ms: 0 };
      case 'memory.list':
      case 'memory.search':
        return { memories: [] };
      case 'memory.get':
        return null;
      case 'skill.list':
        return { skills: [], problems: [] };
      case 'skill.get':
        return { match: null };
      case 'tool.list':
        return {
          tools: [
            { name: 'calculate', risk: 'safe', description: 'Evaluate arithmetic', schema: {} },
            { name: 'get_datetime', risk: 'safe', description: 'Current date/time', schema: {} },
          ],
        };
      case 'health.check':
        return {
          status: 'ok',
          sessions: this.sessions.size,
          provider: 'echo',
          uptime_seconds: (Date.now() - this.startedAt) / 1000,
        };
      case 'sidecar.version':
        return { protocol: '1.0', core: '0.1.0', sidecar: '0.1.0', python: 'browser' };
      default:
        throw new BridgeRpcError({ code: -32601, message: `echo: unknown method ${method}` });
    }
  }
}

// --------------------------------------------------------------------------- //
// The client.
// --------------------------------------------------------------------------- //

/** Selects the real transport under Tauri, else the echo fallback. */
export function defaultTransport(): BridgeTransport {
  return isTauri() ? new TauriBridgeTransport() : new EchoBridgeTransport();
}

export class BridgeClient {
  private transport: BridgeTransport;
  private nextId = 1;
  private handlers = new Set<EventHandler>();
  private _state: BridgeConnectionState;
  private readonly autoSelect: boolean;

  constructor(transport?: BridgeTransport) {
    this.autoSelect = !transport;
    this.transport = transport ?? defaultTransport();
    this._state = this.transport.kind === 'tauri' ? 'connecting' : 'ready';
    this.transport.onState((state) => this.setState(state));
  }

  /** The current connection state. */
  get state(): BridgeConnectionState {
    return this._state;
  }

  /** Which transport is active — `tauri` (sidecar) or `echo` (browser). */
  get transportKind(): 'tauri' | 'echo' {
    return this.transport.kind;
  }

  /** Subscribe to client events. Returns an unsubscribe. */
  on(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  /** Typed request/response. Rejects with `BridgeRpcError` on failure. */
  async call<T>(method: string, params: RpcParams = {}): Promise<T> {
    return this.dispatch<T>(method, params);
  }

  /**
   * Streaming request. `onChunk` fires for each `stream.chunk`; the returned
   * promise resolves with the final result (or rejects with `BridgeRpcError`).
   */
  async stream<T>(method: string, params: RpcParams, handlers: StreamHandlers = {}): Promise<T> {
    return this.dispatch<T>(method, params, (chunk) => {
      this.emit({ type: 'chunk', chunk });
      handlers.onChunk?.(chunk);
    });
  }

  /** Ask the supervisor to restart the sidecar. */
  reconnect(): void {
    this.setState('reconnecting');
    this.transport.reconnect();
  }

  /** Swap the transport (used by tests and by reconnect-with-backoff). */
  setTransport(transport: BridgeTransport): void {
    this.transport = transport;
    this.transport.onState((state) => this.setState(state));
    this.setState(transport.kind === 'tauri' ? 'connecting' : 'ready');
  }

  private async dispatch<T>(
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    const id = this.nextId++;
    try {
      const result = await this.transport.request<T>(id, method, params, onChunk);
      return result;
    } catch (err) {
      const error = toBridgeError(err);
      this.emit({ type: 'error', error });
      throw error;
    }
  }

  private setState(state: BridgeConnectionState): void {
    if (this._state === state) return;
    this._state = state;
    this.emit({ type: 'state', state });
  }

  private emit(event: BridgeClientEvent): void {
    for (const handler of this.handlers) handler(event);
  }

  /** Whether the auto-selected transport is the echo fallback. */
  get isFallback(): boolean {
    return this.autoSelect && this.transport.kind === 'echo';
  }
}

/** A process-wide default client, lazily created. */
let defaultClient: BridgeClient | undefined;

export function getBridgeClient(): BridgeClient {
  if (!defaultClient) defaultClient = new BridgeClient();
  return defaultClient;
}

/** Test helper: reset the singleton (vitest `beforeEach`). */
export function resetBridgeClient(): void {
  defaultClient = undefined;
}
