/** Memory explorer — placeholder shell; implemented in a later phase. */

import { Database } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';

export function MemoryRoute() {
  return (
    <EmptyState
      icon={Database}
      title="Memory explorer"
      description="Semantic, episodic and procedural memories with a dual-calendar timeline. Built in P-02."
    />
  );
}
