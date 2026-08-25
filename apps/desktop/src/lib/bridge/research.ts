/**
 * Typed wrappers for the `research.*` RPC family (P2).
 *
 * Mirrors the P1 contract so obviously bad input never leaves the renderer.
 * The echo mock (`echo-research.ts`) provides deterministic offline data so
 * the workbench renders without a sidecar.
 */

import type { BridgeClient, StreamHandlers } from './client';
import type {
  ResearchCostEstimate,
  ResearchCreateParams,
  ResearchModifyPlanParams,
  ResearchPlan,
  ResearchProgressEvent,
  ResearchReport,
  ResearchSession,
  ResearchStep,
} from './research-types';

// --------------------------------------------------------------------------- //
// Validation helpers
// --------------------------------------------------------------------------- //

/** Client-side validation for research.create params. Returns an error or null. */
export function validateResearchCreate(params: ResearchCreateParams): string | null {
  if (!params.topic.trim()) return 'Topic must not be empty.';
  if (params.topic.length > 500) return 'Topic must be at most 500 characters.';
  if (!params.objective.trim()) return 'Objective must not be empty.';
  if (params.objective.length > 2_000) return 'Objective must be at most 2,000 characters.';
  if (!['simple', 'deep'].includes(params.depth)) return 'Depth must be "simple" or "deep".';
  if (params.max_iterations !== undefined && params.max_iterations < 1) {
    return 'max_iterations must be ≥ 1.';
  }
  if (params.max_time_seconds !== undefined && params.max_time_seconds < 30) {
    return 'max_time_seconds must be ≥ 30.';
  }
  return null;
}

/** Client-side validation for plan modification. */
export function validateResearchPlan(plan: ResearchPlan): string | null {
  if (!plan.research_questions.length) return 'Plan must have at least one research question.';
  if (!plan.outline.length) return 'Plan must have at least one outline section.';
  if (plan.methodology.length > 5_000) return 'Methodology must be at most 5,000 characters.';
  return null;
}

// --------------------------------------------------------------------------- //
// Credential redaction (defensive frontend layer)
// --------------------------------------------------------------------------- //

const SECRET_PATTERNS: RegExp[] = [
  /sk-[A-Za-z0-9]{20,}/g,
  /ghp_[A-Za-z0-9]{36}/g,
  /xox[bpa]-[A-Za-z0-9-]{10,}/g,
  /AKIA[A-Z0-9]{16}/g,
  /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g,
];

/**
 * Redact credential-shaped strings from arbitrary text.
 * The backend is expected to redact first; this is a defensive second pass.
 */
export function redactSecrets(text: string): string {
  let result = text;
  for (const pattern of SECRET_PATTERNS) {
    result = result.replace(pattern, '[REDACTED]');
  }
  return result;
}

// --------------------------------------------------------------------------- //
// RPC wrappers
// --------------------------------------------------------------------------- //

/** List all research sessions. */
export function researchList(client: BridgeClient): Promise<{ sessions: ResearchSession[] }> {
  return client.call('research.list', {});
}

/** Get a single research session. */
export function researchGet(client: BridgeClient, sessionId: string): Promise<ResearchSession> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  return client.call('research.get', { session_id: sessionId });
}

/** Create a new research session. */
export function researchCreate(
  client: BridgeClient,
  params: ResearchCreateParams,
): Promise<ResearchSession> {
  const error = validateResearchCreate(params);
  if (error) return Promise.reject(new Error(error));
  return client.call('research.create', {
    topic: params.topic,
    objective: params.objective,
    depth: params.depth,
    data_sources: params.data_sources,
    ...(params.model_route ? { model_route: params.model_route } : {}),
    ...(params.max_iterations !== undefined ? { max_iterations: params.max_iterations } : {}),
    ...(params.max_time_seconds !== undefined ? { max_time_seconds: params.max_time_seconds } : {}),
  });
}

/** Start a research session (triggers planning). */
export function researchStart(client: BridgeClient, sessionId: string): Promise<ResearchSession> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  return client.call('research.start', { session_id: sessionId });
}

/** Approve the plan for a session. */
export function researchApprove(client: BridgeClient, sessionId: string): Promise<ResearchSession> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  return client.call('research.approve', { session_id: sessionId });
}

/** Modify the plan (human-in-the-loop checkpoint). */
export function researchModifyPlan(
  client: BridgeClient,
  params: ResearchModifyPlanParams,
): Promise<ResearchSession> {
  const error = validateResearchPlan(params.plan);
  if (error) return Promise.reject(new Error(error));
  return client.call('research.modify_plan', {
    session_id: params.session_id,
    plan: params.plan,
  });
}

/** Cancel / stop a running session. */
export function researchStop(client: BridgeClient, sessionId: string): Promise<ResearchSession> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  return client.call('research.stop', { session_id: sessionId });
}

/** Get the execution trace for a session. */
export function researchTrace(
  client: BridgeClient,
  sessionId: string,
): Promise<{ steps: ResearchStep[] }> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  return client.call('research.trace', { session_id: sessionId });
}

/** Get the completed report. */
export function researchReport(client: BridgeClient, sessionId: string): Promise<ResearchReport> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  return client.call('research.report', { session_id: sessionId });
}

/** Estimate cost before starting. */
export function researchEstimate(
  client: BridgeClient,
  params: ResearchCreateParams,
): Promise<ResearchCostEstimate> {
  const error = validateResearchCreate(params);
  if (error) return Promise.reject(new Error(error));
  return client.call('research.estimate_cost', {
    topic: params.topic,
    objective: params.objective,
    depth: params.depth,
    data_sources: params.data_sources,
  });
}

/**
 * Subscribe to live streaming progress for a session.
 *
 * Returns a promise that resolves with the final session state when the
 * research completes. `onEvent` fires for each progress event (step started,
 * output, tool call, heartbeat). Use `signal` to cancel.
 */
export function researchStreamProgress(
  client: BridgeClient,
  sessionId: string,
  onEvent: (event: ResearchProgressEvent) => void,
  signal?: AbortSignal,
): Promise<ResearchSession> {
  if (!sessionId.trim()) return Promise.reject(new Error('session id must not be empty'));
  return client.stream<ResearchSession>('research.stream_progress', { session_id: sessionId }, {
    onChunk: (chunk) => {
      // Parse the chunk token as a progress event
      try {
        const event = JSON.parse(chunk.token) as ResearchProgressEvent;
        onEvent(event);
      } catch {
        // Non-JSON chunk — treat as raw output
        onEvent({
          session_id: sessionId,
          event_type: 'output',
          output: chunk.token,
          timestamp: new Date().toISOString(),
        });
      }
    },
    signal,
    timeoutMs: 600_000, // 10 min max for deep research
  } satisfies StreamHandlers);
}

// --------------------------------------------------------------------------- //
// Error mapping — friendly bilingual messages
// --------------------------------------------------------------------------- //

/** Map a domain error to a user-friendly message key. */
export function mapResearchError(error: unknown): {
  key: string;
  fallback: string;
} {
  const message = error instanceof Error ? error.message : String(error);

  if (message.includes('session not found')) {
    return { key: 'errors.sessionNotFound', fallback: 'Research session not found.' };
  }
  if (message.includes('no report')) {
    return { key: 'errors.noReport', fallback: 'No report available yet.' };
  }
  if (message.includes('cancelled')) {
    return { key: 'errors.cancelled', fallback: 'Research was cancelled.' };
  }
  if (message.includes('timed out')) {
    return {
      key: 'errors.timedOut',
      fallback: 'Research timed out. The engine may be busy — try again.',
    };
  }
  if (message.includes('No data sources')) {
    return {
      key: 'errors.noDataSources',
      fallback: 'Attach at least one data source to begin research.',
    };
  }

  return { key: 'errors.unknown', fallback: message };
}
