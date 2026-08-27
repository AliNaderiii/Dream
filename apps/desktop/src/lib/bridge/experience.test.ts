import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { resetEchoExperience } from './echo-experience';
import { experienceApprove, experienceCapture, experienceDeny, experienceList } from './experience';

describe('experience wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoExperience();
  });

  it('keeps a captured skill pending until approve', async () => {
    const client = getBridgeClient();
    const draft = await experienceCapture(client, 'bot_1', 'How do we file notes?');
    expect(draft.status).toBe('APPROVAL_PENDING');
    expect(draft.yolo).toBe(false);
    expect((await experienceList(client, 'bot_1')).count).toBe(1);
    await experienceDeny(client, draft.draft_id);
    expect((await experienceList(client)).count).toBe(0);
    const again = await experienceCapture(client, 'bot_1', 'How do we file notes?');
    const applied = await experienceApprove(client, again.draft_id);
    expect(applied.applied).toBe(true);
  });
});
