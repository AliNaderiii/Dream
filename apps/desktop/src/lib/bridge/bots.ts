/** Typed wrappers for bots.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-bots';

export type { BotRecord } from './echo-bots';

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

export function botsCreate(
  client: BridgeClient,
  spaceId: string,
  name: string,
  roleId = 'secretary',
  model = 'echo',
) {
  return echoOr(
    client,
    () => echo.echoBotsCreate(spaceId, name, roleId, model, false),
    'bots.create',
    { space_id: spaceId, name, role_id: roleId, model, yolo: false },
  );
}

export function botsList(client: BridgeClient, spaceId: string) {
  return echoOr(client, () => echo.echoBotsList(spaceId), 'bots.list', { space_id: spaceId });
}
