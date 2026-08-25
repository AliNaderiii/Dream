/**
 * Research & Analysis workbench route (P2).
 *
 * Auto-registered via the P0 route-registry (research.route.ts). This is the
 * entry point for the research workbench — it renders the ResearchShell
 * which orchestrates list, composer, plan approval, live trace, and report
 * views.
 *
 * Default export is required by the route-registry's lazy loader.
 */

import { ResearchShell } from '@/components/research/research-shell';

export default function ResearchRoute() {
  return <ResearchShell />;
}

/** Named export for consistency with other routes (optional). */
export { ResearchRoute };
