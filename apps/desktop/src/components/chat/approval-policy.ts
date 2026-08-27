import type { BridgeClient } from '@/lib/bridge/client';
import type { ApprovalDecision } from '@/types';

/** Resolve each visible approval choice to the protocol's fail-closed boolean.
 * Only Allow once is allowed. Always Allow / session skip resolve as denied. */
export function resolveApprovalOnBridge(
  client: Pick<BridgeClient, 'call'>,
  approvalId: string,
  decision: ApprovalDecision,
): Promise<unknown> {
  return client.call('approval.resolve', {
    approval_id: approvalId,
    allowed: decision === 'allow_once',
  });
}
