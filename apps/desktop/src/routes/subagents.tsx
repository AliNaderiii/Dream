/** Subagents — placeholder shell; implemented in a later phase. */

import { Bot } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';

export function SubagentsRoute() {
  return (
    <EmptyState
      icon={Bot}
      title="Subagents"
      description="Live subagent monitoring, logs and review. Built in P-03."
    />
  );
}
