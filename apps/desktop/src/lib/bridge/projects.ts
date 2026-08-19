/**
 * Typed wrappers for the `project.*` RPC family (S06).
 *
 * A project is a folder-like grouping of sessions — never a CRM record.
 * Deleting a project ungroups its sessions; it never deletes a conversation.
 * The server owns validation; these wrappers only shape the params.
 */

import type { BridgeClient } from './client';
import type { BridgeProject, ProjectListResult } from './types';

/** Result shapes shared by the mutation RPCs. */
export interface ProjectDeleteResult {
  deleted: boolean;
  project_id: string;
}

/** All projects, most recently touched first. */
export function listProjects(client: BridgeClient): Promise<ProjectListResult> {
  return client.call<ProjectListResult>('project.list', {});
}

/** One project; `project.get` also joins the sessions it groups. */
export function getProject(client: BridgeClient, projectId: string): Promise<BridgeProject> {
  return client.call<BridgeProject>('project.get', { project_id: projectId });
}

/** Create a project. `folder` is the workspace folder path, optional. */
export function createProject(
  client: BridgeClient,
  draft: { name: string; folder?: string | null; session_ids?: string[] },
): Promise<BridgeProject> {
  const params: Record<string, unknown> = { name: draft.name };
  if (draft.folder !== undefined) params['folder'] = draft.folder;
  if (draft.session_ids !== undefined) params['session_ids'] = draft.session_ids;
  return client.call<BridgeProject>('project.create', params);
}

/** Rename a project and/or change its workspace folder (`null` clears it). */
export function updateProject(
  client: BridgeClient,
  projectId: string,
  fields: { name?: string; folder?: string | null },
): Promise<BridgeProject> {
  return client.call<BridgeProject>('project.update', { project_id: projectId, ...fields });
}

/** Delete a project. Sessions are ungrouped, never deleted. */
export function deleteProject(
  client: BridgeClient,
  projectId: string,
): Promise<ProjectDeleteResult> {
  return client.call<ProjectDeleteResult>('project.delete', { project_id: projectId });
}

/** Group a session under a project (it leaves any other project). */
export function addSessionToProject(
  client: BridgeClient,
  projectId: string,
  sessionId: string,
): Promise<BridgeProject> {
  return client.call<BridgeProject>('project.add_session', {
    project_id: projectId,
    session_id: sessionId,
  });
}

/** Remove a session from a project without deleting it. */
export function removeSessionFromProject(
  client: BridgeClient,
  projectId: string,
  sessionId: string,
): Promise<BridgeProject> {
  return client.call<BridgeProject>('project.remove_session', {
    project_id: projectId,
    session_id: sessionId,
  });
}
