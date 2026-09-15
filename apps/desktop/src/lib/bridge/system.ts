/**
 * Typed client wrappers for System Hardware Acceleration & Golden Release Bridge RPC.
 */

import type { BridgeClient } from './client';
import * as echo from './echo-system';

export interface HardwareDevice {
  device_type: string;
  device_name: string;
  is_available: boolean;
  total_memory_mb: number;
  free_memory_mb: number;
  compute_capability: string;
  driver_version?: string;
}

export interface AccelerationProfile {
  active_backend: string;
  speculative_streaming: boolean;
  zero_latency_mode: boolean;
  adaptive_compaction: boolean;
  draft_buffer_size: number;
  first_token_latency_ms: number;
  tokens_per_second: number;
  vram_allocated_mb: number;
  devices: HardwareDevice[];
}

export interface HardwareBenchmarkResult {
  status: string;
  backend: string;
  measured_latency_ms: number;
  estimated_throughput_tps: number;
  memory_bandwidth_gbs: number;
  timestamp: number;
}

export interface GoldenReleaseInfo {
  release_version: string;
  release_tag: string;
  codename: string;
  python_version: string;
  platform_system: string;
  platform_machine: string;
  total_subsystems_count: number;
  verified_subsystems: string[];
  readiness_score: number;
  is_golden_release: boolean;
}

export interface SystemDiagnostics {
  status: string;
  diagnostic_id: string;
  timestamp: number;
  profile: AccelerationProfile;
  system_info: {
    platform: string;
    python: string;
    cpu_count: number;
  };
  signature: string;
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

export function systemGetHardwareStatus(
  client: BridgeClient,
): Promise<{ status: string; profile: AccelerationProfile }> {
  return echoOr(client, () => echo.echoSystemGetHardwareStatus(), 'system.get_hardware_status', {});
}

export function systemConfigureAcceleration(
  client: BridgeClient,
  config: {
    speculative_streaming?: boolean;
    zero_latency_mode?: boolean;
    adaptive_compaction?: boolean;
    draft_buffer_size?: number;
  },
): Promise<{ status: string; profile: AccelerationProfile }> {
  return echoOr(
    client,
    () => echo.echoSystemConfigureAcceleration(config),
    'system.configure_acceleration',
    config,
  );
}

export function systemBenchmarkHardware(
  client: BridgeClient,
): Promise<{ status: string; benchmark: HardwareBenchmarkResult }> {
  return echoOr(client, () => echo.echoSystemBenchmarkHardware(), 'system.benchmark_hardware', {});
}

export function systemGetGoldenReleaseInfo(client: BridgeClient): Promise<GoldenReleaseInfo> {
  return echoOr(
    client,
    () => echo.echoSystemGetGoldenReleaseInfo(),
    'system.get_golden_release_info',
    {},
  );
}

export function systemExportDiagnostics(client: BridgeClient): Promise<SystemDiagnostics> {
  return echoOr(client, () => echo.echoSystemExportDiagnostics(), 'system.export_diagnostics', {});
}

export function systemReset(client: BridgeClient): Promise<{ status: string }> {
  return echoOr(client, () => echo.echoSystemReset(), 'system.reset', {});
}
