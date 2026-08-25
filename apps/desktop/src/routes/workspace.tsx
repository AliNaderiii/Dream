/**
 * Workspace workbench route.
 *
 * Auto-registered via the P0 route-registry (workspace.route.ts).
 * Default export is required by the lazy loader.
 */

import { WorkspaceShell } from '@/components/workspace/workspace-shell';

export default function WorkspaceRoute() {
  return <WorkspaceShell />;
}

export { WorkspaceRoute };
