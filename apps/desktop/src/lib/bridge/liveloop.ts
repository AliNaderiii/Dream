/** Typed wrappers for liveloop.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-liveloop';

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

export function liveloopRouteSnapshot(
  client: BridgeClient,
  bar?: string,
  pane?: string,
  model?: string,
) {
  return echoOr(client, () => echo.echoRouteSnapshot(bar, pane, model), 'liveloop.route_snapshot', {
    ...(bar ? { bar_provider: bar } : {}),
    ...(pane ? { pane_provider: pane } : {}),
    ...(model ? { pane_model: model } : {}),
  });
}

export function liveloopArmDraft(client: BridgeClient, draftId: string, approved = false) {
  return echoOr(client, () => echo.echoArmDraft(draftId, approved), 'liveloop.arm_draft', {
    draft_id: draftId,
    approved,
  });
}

export function liveloopRoleTurn(
  client: BridgeClient,
  spaceId: string,
  roleId: string,
  question: string,
  live = false,
) {
  return echoOr(
    client,
    () => echo.echoRoleTurn(spaceId, roleId, question, live),
    'liveloop.role_turn',
    { space_id: spaceId, role_id: roleId, question, live },
  );
}
