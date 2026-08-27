/** Typed wrappers for experience.*. Never edits client.ts. */

import type { BridgeClient } from './client';
import * as echo from './echo-experience';

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

export function experienceCapture(client: BridgeClient, botId: string, question: string) {
  return echoOr(
    client,
    () => echo.echoExperienceCapture(botId, question, false),
    'experience.capture',
    { bot_id: botId, question, yolo: false },
  );
}

export function experienceList(client: BridgeClient, botId?: string) {
  return echoOr(client, () => echo.echoExperienceList(botId), 'experience.list', {
    ...(botId ? { bot_id: botId } : {}),
  });
}

export function experienceApprove(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoExperienceApprove(draftId, true), 'experience.approve', {
    draft_id: draftId,
    approved: true,
  });
}

export function experienceDeny(client: BridgeClient, draftId: string) {
  return echoOr(client, () => echo.echoExperienceDeny(draftId), 'experience.deny', {
    draft_id: draftId,
  });
}
