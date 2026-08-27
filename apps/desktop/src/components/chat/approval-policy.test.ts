import { describe, expect, it, vi } from 'vitest';

import { resolveApprovalOnBridge } from '@/components/chat/approval-policy';
import type { BridgeClient } from '@/lib/bridge/client';
import type { ApprovalDecision } from '@/types';

describe('approval bridge policy', () => {
  it.each<[ApprovalDecision, boolean]>([
    ['allow_once', true],
    ['allow_always_session', false],
    ['deny', false],
  ])('wires %s to approval.resolve allowed=%s', async (decision, allowed) => {
    const call = vi.fn().mockResolvedValue({});
    const client = { call } as unknown as Pick<BridgeClient, 'call'>;
    await resolveApprovalOnBridge(client, 'approval-7', decision);
    expect(call).toHaveBeenCalledTimes(1);
    expect(call).toHaveBeenCalledWith('approval.resolve', {
      approval_id: 'approval-7',
      allowed,
    });
  });
});
