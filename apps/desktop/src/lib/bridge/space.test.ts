import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { resetEchoSpace } from './echo-space';
import {
  spaceAsk,
  spaceAttachFolder,
  spaceCreate,
  spaceDenyDraft,
  spaceList,
  spaceProposeDraft,
  spaceSetInstruction,
} from './space';

describe('space wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoSpace();
  });

  it('uses echo when transportKind is echo', async () => {
    const client = getBridgeClient();
    expect(client.transportKind).toBe('echo');
    const created = await spaceCreate(client, 'Lab', 'en', 'safe');
    const listed = await spaceList(client);
    expect(listed.spaces.some((row) => row.space_id === created.space_id)).toBe(true);
    await spaceSetInstruction(client, created.space_id, 'Stay local.');
    const answer = await spaceAsk(client, created.space_id, 'secretary', 'What is the constraint?');
    expect(answer.hosted).toBe(false);
    expect(answer.answer).toContain('Stay local.');
  });

  it('refuses traversal and denied drafts stay idle', async () => {
    const client = getBridgeClient();
    const created = await spaceCreate(client, 'Tight');
    await expect(spaceAttachFolder(client, created.space_id, '../etc')).rejects.toThrow(
      /traversal/,
    );
    const draft = await spaceProposeDraft(client, created.space_id, 'every monday at 10:30');
    const denied = await spaceDenyDraft(client, draft.draft_id);
    expect(denied.status).toBe('DENIED');
  });
});
