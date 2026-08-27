/** Typed wrappers for browse.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-browse';

export type { BrowseDraft, BrowseLink } from './echo-browse';

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

export function browsePropose(client: BridgeClient, url: string) {
  return echoOr(client, () => echo.echoBrowsePropose(url, false), 'browse.propose', {
    url,
    yolo: false,
  });
}

export function browseList(client: BridgeClient) {
  return echoOr(client, () => echo.echoBrowseList(), 'browse.list', {});
}

export function browseGet(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoBrowseGet(draftId), 'browse.get', { draft_id: draftId });
}

export function browseApprove(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoBrowseApprove(draftId, true), 'browse.approve', {
    draft_id: draftId,
    approved: true,
  });
}

export function browseDeny(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoBrowseDeny(draftId), 'browse.deny', { draft_id: draftId });
}

export function browseFollow(client: BridgeClient, draftId: string, url: string) {
  return echoOr(client, () => echo.echoBrowseFollow(draftId, url, false), 'browse.follow', {
    draft_id: draftId,
    url,
    yolo: false,
  });
}
