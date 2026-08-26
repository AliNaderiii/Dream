/** Typed wrappers for remotegw.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-remotegw';

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

export function remotegwStatus(client: BridgeClient) {
  return echoOr(client, () => echo.echoRemoteStatus(), 'remotegw.status', {});
}

export function remotegwPreview(client: BridgeClient, host?: string, lan = false) {
  return echoOr(client, () => echo.echoRemotePreview(host, lan), 'remotegw.preview', {
    ...(host ? { host } : {}),
    lan,
  });
}

export function remotegwStart(client: BridgeClient) {
  return echoOr(client, () => echo.echoRemoteStart(), 'remotegw.start', {});
}

export function remotegwStop(client: BridgeClient) {
  return echoOr(client, () => echo.echoRemoteStop(), 'remotegw.stop', {});
}

export function remotegwIssueToken(client: BridgeClient, scope = 'read', label = 'Remote') {
  return echoOr(client, () => echo.echoRemoteIssue(scope, label), 'remotegw.issue_token', {
    scope,
    label,
  });
}
