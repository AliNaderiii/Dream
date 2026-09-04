/**
 * Error classes for the Dream bridge.
 *
 * `BridgeRpcError` carries the JSON-RPC error code and optional structured
 * data (e.g. an `approval_id`), so the UI can branch on taxonomy rather than
 * parsing strings. `isRetryable` tells the caller whether to back off and try
 * again (rate limit / resource exhaustion) versus surface a hard failure.
 */

import { RPC_ERROR, type RpcErrorObject } from './types';

/**
 * Where a failure came from. Lets callers tell a renderer-side deadline or
 * cancellation apart from a sidecar error without parsing messages:
 *
 * - `rpc`       — the sidecar's handler returned a taxonomy error;
 * - `transport` — the Rust shell could not deliver the request or lost the
 *                 sidecar while it was in flight (tagged `data.kind`);
 * - `timeout`   — this client's own deadline (`timeoutMs`) elapsed;
 * - `cancelled` — the caller's `AbortSignal` fired.
 */
export type BridgeErrorKind = 'rpc' | 'transport' | 'timeout' | 'cancelled';

/** A structured RPC failure thrown by `BridgeClient.call` / `stream`. */
export class BridgeRpcError extends Error {
  readonly code: number;
  readonly data: Record<string, unknown> | undefined;
  readonly kind: BridgeErrorKind;

  constructor(
    error: RpcErrorObject | { code: number; message?: string; data?: Record<string, unknown> },
    kind?: BridgeErrorKind,
  ) {
    super(error.message ?? 'bridge error');
    this.name = 'BridgeRpcError';
    this.code = error.code;
    this.data = error.data;
    this.kind = kind ?? kindFromData(this.data);
  }

  /** Renderer deadline elapsed before the sidecar answered. */
  get isTimeout(): boolean {
    return this.kind === 'timeout';
  }

  /** The caller aborted the request. */
  get isCancelled(): boolean {
    return this.kind === 'cancelled';
  }

  /** The shell could not reach, or lost, the sidecar (not a handler error). */
  get isTransport(): boolean {
    return this.kind === 'transport';
  }

  /** Build the error for an elapsed client-side deadline. */
  static timeout(method: string, timeoutMs: number): BridgeRpcError {
    return new BridgeRpcError(
      { code: RPC_ERROR.INTERNAL_ERROR, message: `${method} timed out after ${timeoutMs}ms` },
      'timeout',
    );
  }

  /** Build the error for a caller-initiated cancellation. */
  static cancelled(method: string): BridgeRpcError {
    return new BridgeRpcError(
      { code: RPC_ERROR.INTERNAL_ERROR, message: `${method} was cancelled` },
      'cancelled',
    );
  }

  /** True for transient errors the caller may retry with backoff. */
  get isRetryable(): boolean {
    return this.code === RPC_ERROR.RATE_LIMITED || this.code === RPC_ERROR.RESOURCE_EXHAUSTED;
  }

  /** True when a dangerous tool is waiting on a human approval. */
  get isApprovalRequired(): boolean {
    return this.code === RPC_ERROR.APPROVAL_REQUIRED;
  }

  /** The approval id when present, else null. */
  get approvalId(): string | null {
    const id = this.data?.['approval_id'];
    return typeof id === 'string' ? id : null;
  }
}

/**
 * Wraps a thrown value as a `BridgeRpcError`.
 *
 * Tauri command failures arrive as strings; structured RPC errors arrive as
 * objects. This normalises both, and any unknown failure becomes an internal
 * error so the UI always has a typed error to render.
 */
export function toBridgeError(value: unknown): BridgeRpcError {
  if (value instanceof BridgeRpcError) return value;
  if (value && typeof value === 'object' && 'code' in value && typeof value.code === 'number') {
    return new BridgeRpcError(value as RpcErrorObject);
  }
  const message =
    typeof value === 'string' ? value : ((value as Error)?.message ?? 'unknown error');
  return new BridgeRpcError({ code: RPC_ERROR.INTERNAL_ERROR, message });
}

/**
 * The Rust shell tags every error it originates (not-connected, sidecar
 * restarted, sidecar closed, reserved id) with `data.kind = "transport"`, and
 * its own deadline with `data.kind = "timeout"`; anything else is a sidecar
 * handler error. The numeric codes are unchanged, so older shells that send
 * no tag simply classify as `rpc`.
 */
function kindFromData(data: Record<string, unknown> | undefined): BridgeErrorKind {
  const tag = data?.['kind'];
  if (tag === 'transport') return 'transport';
  if (tag === 'timeout') return 'timeout';
  return 'rpc';
}
