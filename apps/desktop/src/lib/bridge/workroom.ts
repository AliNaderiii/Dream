/** Typed wrappers for workroom.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-workroom';

export type { WorkroomDraft, WorkroomRecord, WorkroomSeat } from './echo-workroom';

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

export function workroomCreate(client: BridgeClient, name: string) {
  return echoOr(client, () => echo.echoWorkroomCreate(name, false), 'workroom.create', {
    name,
    yolo: false,
  });
}

export function workroomList(client: BridgeClient) {
  return echoOr(client, () => echo.echoWorkroomList(), 'workroom.list', {});
}

export function workroomGet(client: BridgeClient, roomId: string) {
  return echoOr(client, () => echo.echoWorkroomGet(roomId), 'workroom.get', { room_id: roomId });
}

export function workroomAddSeat(
  client: BridgeClient,
  roomId: string,
  name: string,
  roleId = 'specialist',
  vip = false,
) {
  return echoOr(
    client,
    () => echo.echoWorkroomAddSeat(roomId, name, roleId, vip, false),
    'workroom.add_seat',
    { room_id: roomId, name, role_id: roleId, vip, yolo: false },
  );
}

export function workroomListSeats(client: BridgeClient, roomId: string) {
  return echoOr(client, () => echo.echoWorkroomListSeats(roomId), 'workroom.list_seats', {
    room_id: roomId,
  });
}

export function workroomDraft(client: BridgeClient, roomId: string, body: string) {
  return echoOr(client, () => echo.echoWorkroomDraft(roomId, body, false), 'workroom.draft', {
    room_id: roomId,
    body,
    yolo: false,
  });
}

export function workroomListDrafts(client: BridgeClient, roomId: string) {
  return echoOr(client, () => echo.echoWorkroomListDrafts(roomId), 'workroom.list_drafts', {
    room_id: roomId,
  });
}

export function workroomApprove(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoWorkroomApprove(draftId, true), 'workroom.approve', {
    draft_id: draftId,
    approved: true,
  });
}

export function workroomDeny(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoWorkroomDeny(draftId), 'workroom.deny', {
    draft_id: draftId,
  });
}
