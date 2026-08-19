/**
 * Deterministic echo runtime for the `project.*` RPC family (S06).
 *
 * Browser dev and vitest have no sidecar, so the projects screen renders
 * against this in-memory model. It reproduces the observable contract of the
 * `project.*` handlers in `dream/bridge/methods.py`: same wire shapes, same
 * validation errors, same one-project-per-session rule, and the same
 * delete semantics — deleting a project ungroups its sessions, it never
 * deletes a conversation.
 */

import { BridgeRpcError } from './errors';
import type { BridgeProject, ProjectListResult, RpcParams } from './types';
import { RPC_ERROR } from './types';

let counter = 0;

const nextId = (): string => `prj_echo_${(++counter).toString(16).padStart(4, '0')}`;

/** Seconds since the epoch, matching the sidecar's float timestamps. */
const now = (): number => Date.now() / 1000;

function invalidParams(message: string): BridgeRpcError {
  return new BridgeRpcError({ code: RPC_ERROR.INVALID_PARAMS, message });
}

function str(params: RpcParams, key: string, fallback = ''): string {
  const value = params[key];
  return typeof value === 'string' ? value : fallback;
}

/** Deduplicate a session-id list, keeping first-seen order (sidecar parity). */
function cleanSessionIds(value: unknown): string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) throw invalidParams('session_ids must be a list of strings');
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const item of value) {
    if (typeof item !== 'string' || !item.trim()) {
      throw invalidParams('session_ids entries must be non-empty strings');
    }
    if (!seen.has(item)) {
      seen.add(item);
      cleaned.push(item);
    }
  }
  return cleaned;
}

export class EchoProjectsRuntime {
  private projects = new Map<string, BridgeProject>();

  /**
   * Builds the runtime. `sessionExists` lets the echo transport enforce the
   * sidecar's rule that only known sessions can join a project; without it
   * (standalone tests) any id is accepted.
   */
  constructor(private readonly sessionExists?: (sessionId: string) => boolean) {}

  create(params: RpcParams): BridgeProject {
    const name = str(params, 'name').trim();
    if (!name) throw invalidParams('name must be a non-empty string');
    const folderRaw = params['folder'];
    if (folderRaw !== undefined && folderRaw !== null) {
      if (typeof folderRaw !== 'string' || !folderRaw.trim()) {
        throw invalidParams('folder must be a non-empty string when set');
      }
    }
    const timestamp = now();
    const project: BridgeProject = {
      project_id: '',
      id: '',
      name,
      folder: typeof folderRaw === 'string' ? folderRaw.trim() : null,
      session_ids: cleanSessionIds(params['session_ids']),
      created_at: timestamp,
      updated_at: timestamp,
    };
    const id = nextId();
    project.project_id = id;
    project.id = id;
    this.projects.set(id, project);
    return { ...project, session_ids: [...project.session_ids] };
  }

  list(_params: RpcParams): ProjectListResult {
    const projects = [...this.projects.values()]
      .sort((a, b) => b.updated_at - a.updated_at)
      .map((p) => ({ ...p, session_ids: [...p.session_ids] }));
    return { projects };
  }

  get(params: RpcParams): BridgeProject & { sessions: never[] } {
    const project = this.require(params);
    // The echo transport joins no session rows here; the projects screen
    // loads `session.list` itself, exactly as it does against the sidecar.
    return { ...project, session_ids: [...project.session_ids], sessions: [] };
  }

  update(params: RpcParams): BridgeProject {
    const project = this.require(params);
    if ('name' in params) {
      const name = str(params, 'name').trim();
      if (!name) throw invalidParams('name must be a non-empty string');
      project.name = name;
    }
    if ('folder' in params) {
      const folder = params['folder'];
      if (folder === null || (typeof folder === 'string' && !folder.trim())) {
        project.folder = null;
      } else if (typeof folder === 'string') {
        project.folder = folder.trim();
      } else {
        throw invalidParams('folder must be a string or null');
      }
    }
    project.updated_at = now();
    return { ...project, session_ids: [...project.session_ids] };
  }

  delete(params: RpcParams): { deleted: boolean; project_id: string } {
    const project = this.require(params);
    this.projects.delete(project.id);
    return { deleted: true, project_id: project.id };
  }

  addSession(params: RpcParams): BridgeProject {
    const project = this.require(params);
    const sessionId = str(params, 'session_id').trim();
    if (!sessionId) throw invalidParams('session_id must be a non-empty string');
    if (this.sessionExists && !this.sessionExists(sessionId)) {
      throw invalidParams(`no session with id '${sessionId}'`);
    }
    if (!project.session_ids.includes(sessionId)) project.session_ids.push(sessionId);
    // A session belongs to one project: lift it out of any other.
    for (const other of this.projects.values()) {
      if (other.id !== project.id) {
        other.session_ids = other.session_ids.filter((id) => id !== sessionId);
      }
    }
    project.updated_at = now();
    return { ...project, session_ids: [...project.session_ids] };
  }

  removeSession(params: RpcParams): BridgeProject {
    const project = this.require(params);
    const sessionId = str(params, 'session_id').trim();
    if (!sessionId) throw invalidParams('session_id must be a non-empty string');
    project.session_ids = project.session_ids.filter((id) => id !== sessionId);
    project.updated_at = now();
    return { ...project, session_ids: [...project.session_ids] };
  }

  // ----------------------------------------------------------------- //

  private require(params: RpcParams): BridgeProject {
    const id = str(params, 'project_id') || str(params, 'id');
    if (!id) throw invalidParams('project_id must be a non-empty string');
    const project = this.projects.get(id);
    if (!project) throw invalidParams(`no project with id '${id}'`);
    return project;
  }
}
