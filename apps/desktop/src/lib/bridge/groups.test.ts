import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { echoGroupsStart, resetEchoGroups } from './echo-groups';
import { groupsStart } from './groups';

describe('groups wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoGroups();
  });

  it('caps a group at three rounds and refuses YOLO', async () => {
    const client = getBridgeClient();
    await expect(groupsStart(client, 'spc_1', ['bot_a'], 'Plan notes')).rejects.toThrow(/2 to 6/);
    expect(() => echoGroupsStart('spc_1', ['bot_a', 'bot_b'], 'Plan notes', true)).toThrow(/YOLO/);
    const run = await groupsStart(client, 'spc_1', ['bot_a', 'bot_b'], 'Plan notes');
    expect(run.yolo).toBe(false);
    expect(run.hosted).toBe(false);
    expect(run.cap).toBe(3);
    expect(run.rounds).toBe(3);
    expect(run.transcript).toHaveLength(6);
    expect(run.transcript.every((turn) => turn.round <= 3)).toBe(true);
  });
});
