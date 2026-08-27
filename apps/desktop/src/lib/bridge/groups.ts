/** Typed wrappers for groups.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-groups';

export type { GroupRun, GroupTurn } from './echo-groups';

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

export function groupsStart(
  client: BridgeClient,
  spaceId: string,
  botIds: string[],
  question: string,
) {
  return echoOr(
    client,
    () => echo.echoGroupsStart(spaceId, botIds, question, false),
    'groups.start',
    { space_id: spaceId, bot_ids: botIds, question, yolo: false, max_rounds: 3 },
  );
}

export function groupsGet(client: BridgeClient, groupId: string) {
  return echoOr(client, () => echo.echoGroupsGet(groupId), 'groups.get', { group_id: groupId });
}

export function groupsList(client: BridgeClient, spaceId: string) {
  return echoOr(client, () => echo.echoGroupsList(spaceId), 'groups.list', { space_id: spaceId });
}
