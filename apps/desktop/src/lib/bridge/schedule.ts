/**
 * Typed wrappers for the `schedule.*` RPC family (S06 UI surface).
 *
 * The parsing, cron engine and daemon live in the sidecar
 * (`dream/scheduler.py`, `dream/nl_schedule.py`); the browser-side
 * `lib/schedule` mirror only powers the live preview. Whatever the user
 * submits is re-parsed by the sidecar, and its verdict wins.
 */

import type { BridgeClient, RequestOptions } from './client';
import type { BridgeApproval, BridgeSchedule, BridgeScheduleRun, SchedulePreview } from './types';

/** `schedule.create` params — either rhythm form is accepted. */
export interface ScheduleDraft {
  name: string;
  prompt: string;
  cron_expression?: string;
  natural_language?: string;
  description?: string;
  session_id?: string | null;
  enabled?: boolean;
  max_runs?: number | null;
  require_approval?: boolean;
}

/** `schedule.get` returns the schedule with its recent history joined. */
export interface ScheduleGetResult extends BridgeSchedule {
  runs: BridgeScheduleRun[];
}

export interface ScheduleListResult {
  schedules: BridgeSchedule[];
}

export interface ScheduleHistoryResult {
  runs: BridgeScheduleRun[];
}

export interface ScheduleRunNowResult {
  schedule: BridgeSchedule;
  run: BridgeScheduleRun | null;
}

export interface ScheduleDeleteResult {
  deleted: boolean;
  schedule_id: string;
}

export function listSchedules(
  client: BridgeClient,
  includeDisabled = true,
  request?: RequestOptions,
): Promise<ScheduleListResult> {
  return client.call<ScheduleListResult>(
    'schedule.list',
    { include_disabled: includeDisabled },
    request,
  );
}

export function getSchedule(
  client: BridgeClient,
  scheduleId: string,
  request?: RequestOptions,
): Promise<ScheduleGetResult> {
  return client.call<ScheduleGetResult>('schedule.get', { schedule_id: scheduleId }, request);
}

export function createSchedule(
  client: BridgeClient,
  draft: ScheduleDraft,
  request?: RequestOptions,
): Promise<BridgeSchedule> {
  const params: Record<string, unknown> = { name: draft.name, prompt: draft.prompt };
  if (draft.cron_expression !== undefined) params['cron_expression'] = draft.cron_expression;
  if (draft.natural_language !== undefined) params['natural_language'] = draft.natural_language;
  if (draft.description !== undefined) params['description'] = draft.description;
  if (draft.session_id !== undefined) params['session_id'] = draft.session_id;
  if (draft.enabled !== undefined) params['enabled'] = draft.enabled;
  if (draft.max_runs !== undefined) params['max_runs'] = draft.max_runs;
  if (draft.require_approval !== undefined) params['require_approval'] = draft.require_approval;
  return client.call<BridgeSchedule>('schedule.create', params, request);
}

export function toggleSchedule(
  client: BridgeClient,
  scheduleId: string,
  enabled?: boolean,
  request?: RequestOptions,
): Promise<BridgeSchedule> {
  const params: Record<string, unknown> = { schedule_id: scheduleId };
  if (enabled !== undefined) params['enabled'] = enabled;
  return client.call<BridgeSchedule>('schedule.toggle', params, request);
}

export function deleteSchedule(
  client: BridgeClient,
  scheduleId: string,
  request?: RequestOptions,
): Promise<ScheduleDeleteResult> {
  return client.call<ScheduleDeleteResult>('schedule.delete', { schedule_id: scheduleId }, request);
}

/**
 * Live prose→cron preview for the create form. Never rejects: a half-typed
 * phrase reports `{valid: false, error}` instead of throwing.
 */
export function previewSchedule(
  client: BridgeClient,
  input: { natural_language?: string; cron_expression?: string },
  options?: RequestOptions,
): Promise<SchedulePreview> {
  return client.call<SchedulePreview>('schedule.preview', { ...input }, options);
}

export function scheduleHistory(
  client: BridgeClient,
  scheduleId: string,
  limit = 20,
  request?: RequestOptions,
): Promise<ScheduleHistoryResult> {
  return client.call<ScheduleHistoryResult>(
    'schedule.history',
    {
      schedule_id: scheduleId,
      limit,
    },
    request,
  );
}

export function runScheduleNow(
  client: BridgeClient,
  scheduleId: string,
  request?: RequestOptions,
): Promise<ScheduleRunNowResult> {
  return client.call<ScheduleRunNowResult>(
    'schedule.run_now',
    { schedule_id: scheduleId },
    request,
  );
}

/** Resolve a pending scheduled-run approval (fail-closed gate G11). */
export function approveScheduleRun(
  client: BridgeClient,
  approvalId: string,
  allowed: boolean,
  request?: RequestOptions,
): Promise<{ approval_id: string; allowed: boolean }> {
  return client.call<{ approval_id: string; allowed: boolean }>(
    'schedule.approve',
    {
      approval_id: approvalId,
      allowed,
    },
    request,
  );
}

/** Pending approvals, for the scheduler's approve/deny queue (S06). */
export function listApprovals(
  client: BridgeClient,
  request?: RequestOptions,
): Promise<{ approvals: BridgeApproval[] }> {
  return client.call<{ approvals: BridgeApproval[] }>('approval.list', {}, request);
}
