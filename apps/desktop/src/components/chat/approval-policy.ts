import type { BridgeClient } from '@/lib/bridge/client';
import type { ApprovalDecision } from '@/types';

/** Resolve each visible approval choice to the protocol's fail-closed boolean. */
export function resolveApprovalOnBridge(
  client: Pick<BridgeClient, 'call'>,
  approvalId: string,
  decision: ApprovalDecision,
): Promise<unknown> {
  return client.call('approval.resolve', {
    approval_id: approvalId,
    allowed: decision !== 'deny',
  });
}
