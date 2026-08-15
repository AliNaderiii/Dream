/** Skills manager — placeholder shell; implemented in a later phase. */

import { Wrench } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';

export function SkillsRoute() {
  return (
    <EmptyState
      icon={Wrench}
      title="Skills manager"
      description="Reusable procedures with match statistics and import/export. Built in P-02."
    />
  );
}
