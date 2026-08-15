/**
 * Error classes for the Dream bridge.
 *
 * `BridgeRpcError` carries the JSON-RPC error code and optional structured
 * data (e.g. an `approval_id`), so the UI can branch on taxonomy rather than
 * parsing strings. `isRetryable` tells the caller whether to back off and try
 * again (rate limit / resource exhaustion) versus surface a hard failure.
 */

import { RPC_ERROR, type RpcErrorObject } from './types';

/** A structured RPC failure thrown by `BridgeClient.call` / `stream`. */
export class BridgeRpcError extends Error {
  readonly code: number;
  readonly data: Record<string, unknown> | undefined;

  constructor(error: RpcErrorObject | { code: number; message?: string }) {
    super(error.message ?? 'bridge error');
    this.name = 'BridgeRpcError';
    this.code = error.code;
    this.data = (error as RpcErrorObject).data;
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
