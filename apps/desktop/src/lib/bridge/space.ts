/** Typed wrappers for the `space.*` RPC family. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-space';
import type { SpaceCeiling, SpaceDraft, SpaceRecord, SpaceRole } from './echo-space';

export type { SpaceCeiling, SpaceDraft, SpaceRecord, SpaceRole };

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

export function spaceCatalog(client: BridgeClient) {
  return echoOr(client, () => echo.echoSpaceCatalog(), 'space.catalog', {});
}

export function spaceCreate(
  client: BridgeClient,
  name: string,
  language = 'en',
  ceiling: SpaceCeiling = 'guarded',
) {
  return echoOr(client, () => echo.echoSpaceCreate(name, language, ceiling), 'space.create', {
    name,
    language,
    ceiling,
  });
}

export function spaceList(client: BridgeClient) {
  return echoOr(client, () => echo.echoSpaceList(), 'space.list', {});
}

export function spaceGet(client: BridgeClient, spaceId: string) {
  return echoOr(client, () => echo.echoSpaceGet(spaceId), 'space.get', { space_id: spaceId });
}

export function spaceArchive(client: BridgeClient, spaceId: string) {
  return echoOr(client, () => echo.echoSpaceArchive(spaceId), 'space.archive', {
    space_id: spaceId,
  });
}

export function spaceAttachFolder(client: BridgeClient, spaceId: string, folder: string) {
  return echoOr(client, () => echo.echoSpaceAttach(spaceId, folder), 'space.attach_folder', {
    space_id: spaceId,
    folder,
  });
}

export function spaceSetInstruction(client: BridgeClient, spaceId: string, text: string) {
  return echoOr(
    client,
    () => echo.echoSpaceSetInstruction(spaceId, text),
    'space.set_instruction',
    { space_id: spaceId, text },
  );
}

export function spaceAsk(client: BridgeClient, spaceId: string, roleId: string, question: string) {
  return echoOr(client, () => echo.echoSpaceAsk(spaceId, roleId, question), 'space.ask', {
    space_id: spaceId,
    role_id: roleId,
    question,
  });
}

export function spaceProposeDraft(client: BridgeClient, spaceId: string, rule: string) {
  return echoOr(client, () => echo.echoSpacePropose(spaceId, rule), 'space.propose_draft', {
    space_id: spaceId,
    rule,
  });
}

export function spaceListDrafts(client: BridgeClient, spaceId: string) {
  return echoOr(client, () => echo.echoSpaceListDrafts(spaceId), 'space.list_drafts', {
    space_id: spaceId,
  });
}

export function spaceApproveDraft(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoSpaceApprove(draftId), 'space.approve_draft', {
    draft_id: draftId,
  });
}

export function spaceDenyDraft(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoSpaceDeny(draftId), 'space.deny_draft', {
    draft_id: draftId,
  });
}
