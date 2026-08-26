import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from './client';
import { resetEchoLiveloop } from './echo-liveloop';
import { liveloopArmDraft, liveloopRoleTurn, liveloopRouteSnapshot } from './liveloop';

describe('liveloop wrappers', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoLiveloop();
  });

  it('flags a mismatch and refuses an unapproved arm', async () => {
    const client = getBridgeClient();
    const shot = await liveloopRouteSnapshot(
      client,
      'Echo (offline)',
      'Earth Runtime',
      'qwen3.6-35b',
    );
    expect(shot.mismatch).toBe(true);
    await expect(liveloopArmDraft(client, 'dft_1', false)).rejects.toThrow(/approver/);
    const turn = await liveloopRoleTurn(client, 'spc_1', 'secretary', 'Hi');
    expect(turn.live).toBe(false);
  });
});
