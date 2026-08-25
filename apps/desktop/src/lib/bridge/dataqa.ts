import { getBridgeClient } from './client';
import { toBridgeError } from './errors';
import { createDomainBridgeClient, type ExtensionRequestOptions } from './extension-client';
import {
  echoDataQaAsk,
  echoDataQaChart,
  echoDataQaCreate,
  echoDataQaDelete,
  echoDataQaDiscover,
  echoDataQaGet,
  echoDataQaReset,
  echoDataQaSessions,
} from './echo-dataqa';
import type { RpcParams, StreamChunk } from './types';

export interface DataQaColumnProfile {
  name: string;
  dtype: string;
  role: string;
  null_count: number;
  unique_count: number;
  minimum?: unknown;
  maximum?: unknown;
  top_values?: Array<{ value: unknown; count: number }>;
}
export interface DataQaProfile {
  dataset_id: string;
  name: string;
  relative_path: string;
  format: string;
  row_count: number;
  sampled_rows: number;
  columns: DataQaColumnProfile[];
  loadable: boolean;
  injection_findings: number;
  infobox: Record<string, unknown>;
}
export interface DataQaCandidate {
  dataset_id: string;
  name: string;
  relative_path: string;
  format: string;
  source: string;
  score: number;
  reasons: string[];
  columns: string[];
  row_count?: number;
  loadable: boolean;
  limitation?: string | null;
  size_bytes: number;
  metadata?: string[];
  profile?: DataQaProfile;
}
export interface DataQaDiscoveryResult {
  query: string;
  source: string;
  count: number;
  candidates: DataQaCandidate[];
}
export interface DataQaSession {
  session_id: string;
  created_at: number;
  updated_at: number;
  dataset: DataQaCandidate;
  profile: DataQaProfile;
  turn_count: number;
  stateful: boolean;
}
export interface DataQaSessionList {
  sessions: DataQaSession[];
}
export interface DataQaChart {
  type: string;
  format: string;
  validated: boolean;
  points: number;
  labels: string[];
  consistency: string;
  svg?: string;
  asset_path?: string;
}
export interface DataQaFinalAnswer {
  status: 'ok' | 'insufficient_data' | 'error' | 'cancelled';
  answer: string;
  summary: string;
  language: string;
  grounded: boolean;
  evidence: {
    dataset: string;
    schema: Record<string, unknown>;
    columns?: string[];
    rows: Array<Record<string, unknown>>;
    rows_considered?: number;
    operation?: string;
  };
  plan: Record<string, unknown>;
  generated_code: string;
  chart: DataQaChart | null;
  warnings: string[];
  sandbox?: { kind: string; network_enabled: boolean };
}
export interface DataQaAskResult {
  session_id: string;
  final_answer: DataQaFinalAnswer;
}

const domain = createDomainBridgeClient('dataqa');
const isEcho = () => getBridgeClient().transportKind === 'echo';
type SessionMethod = 'sessions.create' | 'sessions.list' | 'sessions.get' | 'sessions.delete';

// Extension domain clients deliberately accept a single safe method segment.
// Session RPCs use a nested namespace, so preserve the established client/error
// behaviour while sending their fixed, non-user-controlled full method names.
async function requestSession<T>(method: SessionMethod, params: RpcParams = {}): Promise<T> {
  try {
    return await getBridgeClient().call<T>(`dataqa.${method}`, params);
  } catch (error) {
    throw toBridgeError(error);
  }
}

export async function discoverDataQa(
  query: string,
  source?: string,
): Promise<DataQaDiscoveryResult> {
  return isEcho()
    ? echoDataQaDiscover(query)
    : domain.request('discover', { query, ...(source ? { source } : {}) });
}
export async function createDataQaSession(
  source?: string,
  query = '',
  datasetId?: string,
): Promise<DataQaSession> {
  return isEcho()
    ? echoDataQaCreate()
    : requestSession<DataQaSession>('sessions.create', {
        query,
        ...(source ? { source } : {}),
        ...(datasetId ? { dataset_id: datasetId } : {}),
      });
}
export async function listDataQaSessions(): Promise<DataQaSessionList> {
  return isEcho() ? echoDataQaSessions() : requestSession<DataQaSessionList>('sessions.list');
}
export async function getDataQaSession(sessionId: string): Promise<DataQaSession> {
  return isEcho()
    ? echoDataQaGet(sessionId)
    : requestSession<DataQaSession>('sessions.get', { session_id: sessionId });
}
export async function deleteDataQaSession(
  sessionId: string,
): Promise<{ deleted: boolean; session_id: string }> {
  return isEcho()
    ? echoDataQaDelete(sessionId)
    : requestSession<{ deleted: boolean; session_id: string }>('sessions.delete', {
        session_id: sessionId,
      });
}
export async function askDataQa(
  sessionId: string,
  question: string,
  onChunk?: (chunk: StreamChunk) => void,
  options: ExtensionRequestOptions = {},
): Promise<DataQaAskResult> {
  if (isEcho()) {
    const result = echoDataQaAsk(sessionId, question);
    onChunk?.({ id: 'echo-dataqa', token: result.final_answer.answer });
    return result;
  }
  return domain.stream('ask', { session_id: sessionId, question }, onChunk, options);
}
export async function getDataQaChart(
  sessionId: string,
): Promise<{ session_id: string; chart: DataQaChart }> {
  return isEcho() ? echoDataQaChart(sessionId) : domain.request('chart', { session_id: sessionId });
}
export async function resetDataQa(sessionId: string) {
  return isEcho()
    ? echoDataQaReset(sessionId)
    : domain.request<{ reset: boolean }>('reset', { session_id: sessionId });
}
