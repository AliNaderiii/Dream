/**
 * Typed wrappers for the `providerhubs.*` RPC family (P5).
 *
 * When `client.transportKind === 'echo'`, calls stay in the local echo module.
 * Otherwise they go through the namespaced domain client. Secrets never appear
 * in params, results, or route sentences.
 */

import { getBridgeClient } from './client';
import { createDomainBridgeClient } from './extension-client';
import * as echo from './echo-providerhubs';
import type {
  CatalogEntry,
  DiagnoseResult,
  GatewayState,
  GatewayToolId,
  ParserInfo,
  ProbeResult,
  RouteSnapshot,
  RuntimeKind,
  RuntimeRecord,
} from './echo-providerhubs';

export type {
  CatalogEntry,
  CostTier,
  DiagnoseResult,
  GatewayState,
  GatewayTool,
  GatewayToolId,
  ParserFamily,
  ParserInfo,
  ProbeResult,
  RouteSnapshot,
  RuntimeHealth,
  RuntimeKind,
  RuntimeRecord,
} from './echo-providerhubs';

export { ROUTE_PRIORITY } from './echo-providerhubs';

const domain = createDomainBridgeClient('providerhubs');
const isEcho = () => getBridgeClient().transportKind === 'echo';

export function filterCatalog(entries: CatalogEntry[], query: string): CatalogEntry[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return entries;
  return entries.filter(
    (entry) =>
      entry.id.toLowerCase().includes(needle) ||
      entry.name.toLowerCase().includes(needle) ||
      entry.notes.toLowerCase().includes(needle) ||
      entry.runtimes.some((runtime) => runtime.includes(needle)),
  );
}

export function validateRuntimeId(runtimeId: string): runtimeId is RuntimeKind {
  return ['ollama', 'vllm', 'sglang', 'llamacpp', 'lmstudio', 'generic'].includes(runtimeId);
}

export function listCatalog(query = ''): Promise<{ catalog: CatalogEntry[]; count: number }> {
  if (isEcho()) return Promise.resolve(echo.echoCatalog(query));
  return domain.request('catalog', query ? { query } : {});
}

export function listRuntimes(): Promise<{ runtimes: RuntimeRecord[]; recommended: RuntimeKind }> {
  if (isEcho()) return Promise.resolve(echo.echoRuntimes());
  return domain.request('runtimes');
}

export function runtimeHealth(
  runtimeId: string,
): Promise<{ runtime_id: string; health: string; detected: boolean }> {
  if (!validateRuntimeId(runtimeId)) return Promise.reject(new Error('unknown runtime'));
  if (isEcho()) return Promise.resolve(echo.echoHealth(runtimeId));
  return domain.request('health', { runtime_id: runtimeId });
}

export function listModels(
  runtimeId: string,
): Promise<{ runtime_id: string; models: string[]; selected_model: string }> {
  if (!validateRuntimeId(runtimeId)) return Promise.reject(new Error('unknown runtime'));
  if (isEcho()) return Promise.resolve(echo.echoModels(runtimeId));
  return domain.request('models', { runtime_id: runtimeId });
}

export function selectModel(runtimeId: string, model: string): Promise<RuntimeRecord> {
  if (!validateRuntimeId(runtimeId)) return Promise.reject(new Error('unknown runtime'));
  if (isEcho()) return Promise.resolve(echo.echoSelectModel(runtimeId, model));
  return domain.request('select_model', { runtime_id: runtimeId, model });
}

export function testRuntime(runtimeId: string): Promise<ProbeResult> {
  if (!validateRuntimeId(runtimeId)) return Promise.reject(new Error('unknown runtime'));
  if (isEcho()) return Promise.resolve(echo.echoTest(runtimeId));
  return domain.request('test', { runtime_id: runtimeId });
}

export function diagnoseRuntime(runtimeId: string): Promise<DiagnoseResult> {
  if (!validateRuntimeId(runtimeId)) return Promise.reject(new Error('unknown runtime'));
  if (isEcho()) return Promise.resolve(echo.echoDiagnose(runtimeId));
  return domain.request('diagnose', { runtime_id: runtimeId });
}

export function resolveRoute(): Promise<RouteSnapshot> {
  if (isEcho()) return Promise.resolve(echo.echoRoute());
  return domain.request('route');
}

export function getGateway(): Promise<GatewayState> {
  if (isEcho()) return Promise.resolve(echo.echoGateway());
  return domain.request('gateway');
}

export function updateGateway(params: {
  enabled?: boolean;
  tool_id?: GatewayToolId;
  tool_enabled?: boolean;
  byok?: boolean;
}): Promise<GatewayState> {
  if (isEcho()) return Promise.resolve(echo.echoGatewayUpdate(params));
  return domain.request('gateway_update', { ...params });
}

export function listParsers(): Promise<{ parsers: ParserInfo[] }> {
  if (isEcho()) return Promise.resolve(echo.echoParsers());
  return domain.request('parsers');
}

export function mapProviderHubsError(error: unknown): { key: string; fallback: string } {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes('unknown runtime'))
    return { key: 'errors.unknownRuntime', fallback: 'Unknown runtime. Try another route.' };
  if (message.includes('timed out'))
    return { key: 'errors.timedOut', fallback: 'The probe timed out. Try another route.' };
  return { key: 'errors.unknown', fallback: message };
}
