/** Data workbench — placeholder shell; implemented in a later phase. */

import { BarChart3 } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';

export function DataRoute() {
  return (
    <EmptyState
      icon={BarChart3}
      title="Data workbench"
      description="Data preview grid, cleaning steps, chart builder and reports. Built in P-04."
    />
  );
}
