/** Typed helpers for add-only domain bridge clients. */

import { bridge } from './client';
import { toBridgeError, type BridgeRpcError } from './errors';
import type { RpcParams, StreamChunk } from './types';

export interface ExtensionRequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

/**
 * Creates a namespaced client without exposing transport details to a domain.
 * It preserves the established client timeout, cancellation, stream, and error
 * mapping behaviour.
 */
export function createDomainBridgeClient(domain: string) {
  if (!/^[a-z][a-z0-9_]*$/.test(domain)) throw new Error('unsafe bridge domain name');
  const method = (name: string) => {
    if (!/^[a-z][a-z0-9_]*$/.test(name)) throw new Error('unsafe bridge method name');
    return `${domain}.${name}`;
  };
  return {
    async request<T>(name: string, params: RpcParams = {}, options: ExtensionRequestOptions = {}): Promise<T> {
      try {
        return await bridge.call<T>(method(name), params, options);
      } catch (error) {
        throw toBridgeError(error);
      }
    },
    async stream<T>(
      name: string,
      params: RpcParams = {},
      onChunk?: (chunk: StreamChunk) => void,
      options: ExtensionRequestOptions = {},
    ): Promise<T> {
      try {
        return await bridge.stream<T>(method(name), params, { ...options, onChunk });
      } catch (error) {
        throw toBridgeError(error);
      }
    },
  };
}

export type { BridgeRpcError };
