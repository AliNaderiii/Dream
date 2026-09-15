/** Typed client wrappers for sandbox.* JSON-RPC methods. */

import type { BridgeClient } from './client';
import * as echo from './echo-sandbox';

export interface ExecutionArtifact {
  name: string;
  file_path: string;
  mime_type: string;
  size_bytes: number;
  description_fa: string;
  timestamp: number;
}

export interface ExecutionResult {
  language: string;
  status: 'success' | 'error' | 'timeout' | 'blocked';
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  artifacts: ExecutionArtifact[];
  error_message: string;
  variables_updated: string[];
  timestamp: number;
}

export interface DatasetSummary {
  total_rows: number;
  total_columns: number;
  column_names: string[];
  column_types: Record<string, string>;
  null_counts: Record<string, number>;
  numeric_stats: Record<string, Record<string, number>>;
  sample_preview: Record<string, unknown>[];
}

export interface TerminalBackendInfo {
  type: string;
  is_active: boolean;
  available: boolean;
  details: string;
  latency_ms: number;
  metadata: Record<string, unknown>;
}

export interface SandboxStatusResult {
  status: string;
  total_executions: number;
  total_artifacts: number;
  workspace_dir: string;
  variables_count: number;
  last_execution_status: string;
}

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

export function sandboxRunCode(
  client: BridgeClient,
  code: string,
  language = 'python',
  timeoutSeconds = 15.0,
): Promise<{
  status: string;
  result: ExecutionResult;
}> {
  return echoOr(
    client,
    () => echo.echoSandboxRunCode(code, language, timeoutSeconds),
    'sandbox.run_code',
    { code, language, timeout_seconds: timeoutSeconds },
  );
}

export function sandboxAnalyzeData(
  client: BridgeClient,
  dataOrPath: string,
): Promise<{
  status: string;
  summary: DatasetSummary;
  markdown_report: string;
}> {
  return echoOr(client, () => echo.echoSandboxAnalyzeData(dataOrPath), 'sandbox.analyze_data', {
    data_or_path: dataOrPath,
  });
}

export function sandboxListArtifacts(client: BridgeClient): Promise<{
  status: string;
  artifacts: ExecutionArtifact[];
  count: number;
}> {
  return echoOr(client, () => echo.echoSandboxListArtifacts(), 'sandbox.list_artifacts', {});
}

export function sandboxGetStatus(client: BridgeClient): Promise<SandboxStatusResult> {
  return echoOr(client, () => echo.echoSandboxGetStatus(), 'sandbox.get_status', {});
}

export function sandboxReset(client: BridgeClient): Promise<{
  status: string;
  message: string;
}> {
  return echoOr(client, () => echo.echoSandboxReset(), 'sandbox.reset', {});
}

export function sandboxListBackends(client: BridgeClient): Promise<{
  status: string;
  backends: TerminalBackendInfo[];
  active_backend: string;
}> {
  return echoOr(client, () => echo.echoSandboxListBackends(), 'sandbox.list_backends', {});
}

export function sandboxSetBackend(
  client: BridgeClient,
  backend: string,
): Promise<{
  status: string;
  active_backend: string;
}> {
  return echoOr(client, () => echo.echoSandboxSetBackend(backend), 'sandbox.set_backend', {
    backend,
  });
}
