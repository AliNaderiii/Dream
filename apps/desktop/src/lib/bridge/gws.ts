/** Typed wrappers for gws.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-gws';

function echoOr<T>(
  client: BridgeClient,
  local: () => T,
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  if (client.transportKind === 'echo') {
    try {
      return Promise.resolve(local());
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  }
  return client.call<T>(method, params);
}

export function gwsStatus(client: BridgeClient) {
  return echoOr(client, () => echo.echoGwsStatus(), 'gws.status', {});
}

export function gwsOauthBegin(client: BridgeClient) {
  return echoOr(client, () => echo.echoGwsBegin(), 'gws.oauth_begin', {});
}

export function gwsOauthComplete(client: BridgeClient, state: string, code: string) {
  return echoOr(client, () => echo.echoGwsComplete(state, code), 'gws.oauth_complete', {
    state,
    code,
  });
}

export function gwsDisconnect(client: BridgeClient) {
  return echoOr(client, () => echo.echoGwsDisconnect(), 'gws.disconnect', {});
}
