/**
 * Agent modes workbench route.
 *
 * Auto-registered via the P0 route-registry (agents.route.ts).
 * Default export is required by the lazy loader.
 */

import { AgentsShell } from '@/components/agents/agents-shell';

export default function AgentsRoute() {
  return <AgentsShell />;
}

export { AgentsRoute };
