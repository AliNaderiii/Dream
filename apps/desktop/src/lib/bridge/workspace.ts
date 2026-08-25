/**
 * Typed wrappers for the `workspace.*` RPC family.
 *
 * When `client.transportKind === 'echo'`, calls the echo module locally.
 * The central client is never edited.
 */

import type { BridgeClient } from './client';
import * as echo from './echo-workspace';
import type {
  AgentGoal,
  AgentPlan,
  LiveSubagent,
  WorkspaceEntry,
  WorkspacePreview,
  WorkspaceRoot,
} from './echo-workspace';

export type { AgentGoal, AgentPlan, LiveSubagent, WorkspaceEntry, WorkspacePreview, WorkspaceRoot };

function echoOr<T>(
  client: BridgeClient,
  local: () => T,
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  if (client.transportKind === 'echo') {
    try {
      return Promise.resolve(local());
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  }
  return client.call<T>(method, params);
}

export function workspaceRootsList(client: BridgeClient) {
  return echoOr(client, () => echo.echoRootsList(), 'workspace.roots_list', {});
}

export function workspaceImportFolder(client: BridgeClient, folder: string, name?: string) {
  if (!folder.trim()) return Promise.reject(new Error('folder must be a non-empty string'));
  return echoOr(client, () => echo.echoImportFolder(folder, name), 'workspace.import_folder', {
    folder,
    ...(name ? { name } : {}),
  });
}

export function workspaceUnregister(client: BridgeClient, rootId: string) {
  return echoOr(client, () => echo.echoUnregister(rootId), 'workspace.roots_unregister', {
    root_id: rootId,
  });
}

export function workspaceFilesList(client: BridgeClient, rootId: string, path = '') {
  return echoOr(client, () => echo.echoFilesList(rootId, path), 'workspace.files_list', {
    root_id: rootId,
    path,
  });
}

export function workspaceFilesPreview(client: BridgeClient, rootId: string, path: string) {
  return echoOr(client, () => echo.echoFilesPreview(rootId, path), 'workspace.files_preview', {
    root_id: rootId,
    path,
  });
}

export function workspaceFilesRead(client: BridgeClient, rootId: string, path: string) {
  return echoOr(client, () => echo.echoFilesRead(rootId, path), 'workspace.files_read', {
    root_id: rootId,
    path,
  });
}

export function workspaceProjectSettings(
  client: BridgeClient,
  projectId: string,
  settings?: Record<string, string>,
) {
  return echoOr(
    client,
    () => echo.echoProjectSettings(projectId, settings),
    'workspace.project_settings',
    { project_id: projectId, ...(settings ? { settings } : {}) },
  );
}

export function workspaceMoveSession(client: BridgeClient, projectId: string, sessionId: string) {
  return echoOr(
    client,
    () => echo.echoMoveSession(projectId, sessionId),
    'workspace.project_move_session',
    { project_id: projectId, session_id: sessionId },
  );
}

export function workspacePlan(client: BridgeClient, prompt: string) {
  if (!prompt.trim()) return Promise.reject(new Error('prompt must be a non-empty string'));
  return echoOr(client, () => echo.echoPlan(prompt), 'workspace.agentmode_plan', { prompt });
}

export function workspaceContinue(client: BridgeClient, planId: string) {
  return echoOr(client, () => echo.echoContinue(planId), 'workspace.agentmode_continue', {
    plan_id: planId,
  });
}

export function workspaceGoal(client: BridgeClient, objective: string, criteria: string[]) {
  return echoOr(client, () => echo.echoGoal(objective, criteria), 'workspace.agentmode_goal', {
    objective,
    criteria,
  });
}

export function workspaceStop(client: BridgeClient) {
  return echoOr(client, () => echo.echoStop(), 'workspace.agentmode_stop', {});
}

export function workspaceStatus(client: BridgeClient) {
  return echoOr(client, () => echo.echoStatus(), 'workspace.agentmode_status', {});
}

export function workspaceSubagentsLive(client: BridgeClient) {
  return echoOr(client, () => echo.echoSubagentsLive(), 'workspace.subagents_live', {});
}

export function workspaceRefsParse(client: BridgeClient, text: string) {
  return echoOr(client, () => echo.echoRefsParse(text), 'workspace.refs_parse', { text });
}

export function workspaceRefsFile(client: BridgeClient, rootId: string, path: string) {
  return echoOr(client, () => echo.echoRefsFile(rootId, path), 'workspace.refs_file', {
    root_id: rootId,
    path,
  });
}

export function workspaceRefsConversation(client: BridgeClient, sessionId: string) {
  return echoOr(client, () => echo.echoRefsConversation(sessionId), 'workspace.refs_conversation', {
    session_id: sessionId,
  });
}

export function workspaceCommands(client: BridgeClient, query = '') {
  return echoOr(client, () => echo.echoCommands(query), 'workspace.commands_list', { query });
}

export function workspaceShellPropose(client: BridgeClient, command: string) {
  return echoOr(client, () => echo.echoShellPropose(command), 'workspace.shell_propose', {
    command,
  });
}

export function workspaceShellExecute(client: BridgeClient, approvalId: string, approved = false) {
  return echoOr(
    client,
    () => echo.echoShellExecute(approvalId, approved),
    'workspace.shell_execute',
    {
      approval_id: approvalId,
      approved,
    },
  );
}

export type FileListResult = {
  root_id: string;
  path: string;
  entries: WorkspaceEntry[];
  count: number;
  has_more: boolean;
};

export type StatusResult = {
  running: boolean;
  cancelled: boolean;
  live: boolean;
  plans: AgentPlan[];
  goals: AgentGoal[];
  subagents: LiveSubagent[];
};
