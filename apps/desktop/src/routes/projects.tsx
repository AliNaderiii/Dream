/** Projects — placeholder shell; implemented in a later phase. */

import { FolderKanban } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';

export function ProjectsRoute() {
  return (
    <EmptyState
      icon={FolderKanban}
      title="Projects"
      description="Project dashboards, files and per-project memory. Built in P-03."
    />
  );
}
