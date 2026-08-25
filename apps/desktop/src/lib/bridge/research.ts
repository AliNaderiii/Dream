/**
 * Typed wrappers for the `research.*` RPC family (P2).
 *
 * Calls only the 11 real P1 methods:
 *   research.create | list | get | plan | approve | modify | start | status | stream | stop | export
 *
 * When `client.transportKind === 'echo'`, calls the echo module locally
 * (domain-wrapper pattern). Otherwise calls `client.call` / `client.stream`.
 */

import type { BridgeClient } from './client';
import * as echo from './echo-research';
import type {
  ExportResult,
  PlanResult,
  ResearchCreateParams,
  ResearchListResult,
  ResearchModifyParams,
  ResearchStatusParams,
  ResearchStreamParams,
  SessionRecord,
  SessionSummary,
  StatusResult,
  StreamChunk,
} from './research-types';

// --------------------------------------------------------------------------- //
// Validation
// --------------------------------------------------------------------------- //

export function validateResearchCreate(params: ResearchCreateParams): string | null {
  if (!params.topic.trim()) return 'Topic must not be empty.';
  if (params.topic.length > 500) return 'Topic must be at most 500 characters.';
  if (!params.workspace.trim()) return 'Workspace path must not be empty.';
  return null;
}

// --------------------------------------------------------------------------- //
// Credential redaction (defensive frontend layer)
// --------------------------------------------------------------------------- //

const SECRET_PATTERNS: RegExp[] = [
  /sk-[A-Za-z0-9]{20,}/g,
  /sk_EXAMPLE_not_a_real_key/g,
  /ghp_[A-Za-z0-9]{36}/g,
  /ghp_EXAMPLE_not_a_real_token/g,
  /xox[bpa]-[A-Za-z0-9-]{10,}/g,
  /AKIA[A-Z0-9]{16}/g,
  /AKIA_EXAMPLE_NOTREAL/g,
  /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g,
];

export function redactSecrets(text: string): string {
  let result = text;
  for (const pattern of SECRET_PATTERNS) {
    result = result.replace(pattern, '[REDACTED]');
  }
  return result;
}

// --------------------------------------------------------------------------- //
// RPC wrappers — 11 methods, echo-aware
// --------------------------------------------------------------------------- //

/** `research.list` */
export function researchList(client: BridgeClient): Promise<ResearchListResult> {
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoList());
  }
  return client.call<ResearchListResult>('research.list', {});
}

/** `research.get` */
export function researchGet(client: BridgeClient, sessionId: string): Promise<SessionRecord> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoGet(sessionId));
  }
  return client.call<SessionRecord>('research.get', { session_id: sessionId });
}

/** `research.create` */
export function researchCreate(
  client: BridgeClient,
  params: ResearchCreateParams,
): Promise<SessionSummary> {
  const error = validateResearchCreate(params);
  if (error) return Promise.reject(new Error(error));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoCreate(params));
  }
  return client.call<SessionSummary>('research.create', {
    topic: params.topic,
    workspace: params.workspace,
    ...(params.config ? { config: params.config } : {}),
  });
}

/** `research.plan` */
export function researchPlan(client: BridgeClient, sessionId: string): Promise<PlanResult> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoPlan(sessionId));
  }
  return client.call<PlanResult>('research.plan', { session_id: sessionId });
}

/** `research.approve` */
export function researchApprove(client: BridgeClient, sessionId: string): Promise<PlanResult> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoApprove(sessionId));
  }
  return client.call<PlanResult>('research.approve', { session_id: sessionId });
}

/** `research.modify` */
export function researchModify(
  client: BridgeClient,
  params: ResearchModifyParams,
): Promise<PlanResult> {
  if (!params.session_id.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (!params.changes || Object.keys(params.changes).length === 0) {
    return Promise.reject(new Error('changes must be a non-empty object'));
  }
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoModify(params.session_id, params.changes));
  }
  return client.call<PlanResult>('research.modify', {
    session_id: params.session_id,
    changes: params.changes,
  });
}

/** `research.start` */
export function researchStart(client: BridgeClient, sessionId: string): Promise<SessionSummary> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoStart(sessionId));
  }
  return client.call<SessionSummary>('research.start', { session_id: sessionId });
}

/** `research.status` */
export function researchStatus(
  client: BridgeClient,
  params: ResearchStatusParams,
): Promise<StatusResult> {
  if (!params.session_id.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoStatus(params.session_id, params.cursor ?? 0));
  }
  return client.call<StatusResult>('research.status', {
    session_id: params.session_id,
    ...(params.cursor !== undefined ? { cursor: params.cursor } : {}),
  });
}

/** `research.stream` — streaming live trace. */
export function researchStream(
  client: BridgeClient,
  params: ResearchStreamParams,
  onChunk: (chunk: StreamChunk) => void,
  signal?: AbortSignal,
): Promise<SessionSummary> {
  if (!params.session_id.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return echo.echoStream(params.session_id, params.cursor ?? 0, onChunk, signal);
  }
  return client.stream<SessionSummary>(
    'research.stream',
    {
      session_id: params.session_id,
      ...(params.cursor !== undefined ? { cursor: params.cursor } : {}),
      ...(params.timeout !== undefined ? { timeout: params.timeout } : {}),
      ...(params.follow !== undefined ? { follow: params.follow } : {}),
    },
    {
      onChunk: (chunk) => {
        try {
          const raw: unknown =
            typeof chunk.token === 'string' ? (JSON.parse(chunk.token) as unknown) : chunk.token;
          onChunk(raw as StreamChunk);
        } catch {
          // Non-JSON chunk — wrap as event
          onChunk({
            event: { event: 'output', ts: Date.now() / 1000, text: chunk.token },
            cursor: 0,
          });
        }
      },
      signal,
      timeoutMs: 600_000,
    },
  );
}

/** `research.stop` */
export function researchStop(client: BridgeClient, sessionId: string): Promise<SessionSummary> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoStop(sessionId));
  }
  return client.call<SessionSummary>('research.stop', { session_id: sessionId });
}

/** `research.export` */
export function researchExport(client: BridgeClient, sessionId: string): Promise<ExportResult> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  if (client.transportKind === 'echo') {
    return Promise.resolve(echo.echoExport(sessionId));
  }
  return client.call<ExportResult>('research.export', { session_id: sessionId });
}

// --------------------------------------------------------------------------- //
// Error mapping
// --------------------------------------------------------------------------- //

export function mapResearchError(error: unknown): { key: string; fallback: string } {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes('session not found'))
    return { key: 'errors.sessionNotFound', fallback: 'Research session not found.' };
  if (message.includes('must be approved'))
    return { key: 'errors.notApproved', fallback: 'The plan must be approved before starting.' };
  if (message.includes('nothing to approve'))
    return { key: 'errors.nothingToApprove', fallback: 'Nothing to approve in the current state.' };
  if (message.includes('timed out') || message.includes('exceeded'))
    return {
      key: 'errors.timedOut',
      fallback: 'Research timed out. The engine may be busy — try again.',
    };
  if (message.includes('cancelled'))
    return { key: 'errors.cancelled', fallback: 'Research was cancelled.' };
  if (message.includes('only a COMPLETE'))
    return { key: 'errors.notComplete', fallback: 'Only a complete session can be exported.' };
  return { key: 'errors.unknown', fallback: message };
}
