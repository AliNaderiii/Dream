import { describe, expect, it } from 'vitest';
import { BridgeClient, EchoBridgeTransport } from './client';
import {
  systemBenchmarkHardware,
  systemConfigureAcceleration,
  systemExportDiagnostics,
  systemGetGoldenReleaseInfo,
  systemGetHardwareStatus,
  systemReset,
} from './system';

const mockClient = new BridgeClient(new EchoBridgeTransport());

describe('System Bridge Client (Echo Mode)', () => {
  it('gets hardware status and acceleration profile', async () => {
    const status = await systemGetHardwareStatus(mockClient);
    expect(status.status).toBe('healthy');
    expect(status.profile.active_backend).toBe('cuda');
    expect(status.profile.devices.length).toBeGreaterThanOrEqual(1);
  });

  it('configures speculative zero-latency parameters', async () => {
    const cfg = await systemConfigureAcceleration(mockClient, {
      speculative_streaming: true,
      draft_buffer_size: 6,
    });
    expect(cfg.status).toBe('configured');
    expect(cfg.profile.draft_buffer_size).toBe(6);
  });

  it('runs hardware compute benchmark', async () => {
    const bench = await systemBenchmarkHardware(mockClient);
    expect(bench.status).toBe('completed');
    expect(bench.benchmark.measured_latency_ms).toBeGreaterThan(0);
  });

  it('retrieves golden release v4.0.0 info', async () => {
    const info = await systemGetGoldenReleaseInfo(mockClient);
    expect(info.release_version).toBe('4.0.0');
    expect(info.total_subsystems_count).toBe(52);
    expect(info.is_golden_release).toBe(true);
    expect(info.readiness_score).toBe(100.0);
  });

  it('exports system diagnostics bundle', async () => {
    const diag = await systemExportDiagnostics(mockClient);
    expect(diag.status).toBe('exported');
    expect(diag.signature).toBeDefined();
  });

  it('resets system acceleration state', async () => {
    const resetRes = await systemReset(mockClient);
    expect(resetRes.status).toBe('reset');
  });
});
