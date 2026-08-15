/** Provenance — placeholder shell; implemented in a later phase. */

import { GitBranch } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';

export function ProvenanceRoute() {
  return (
    <EmptyState
      icon={GitBranch}
      title="Provenance"
      description="Run history and the run to turn to tool to artifact tree. Built in P-03."
    />
  );
}
