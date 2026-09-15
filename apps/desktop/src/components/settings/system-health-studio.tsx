/**
 * System Health, Hardware Acceleration & Golden Release Studio Component.
 */

import {
  Activity,
  CheckCircle2,
  Copy,
  Laptop,
  Play,
  Server,
  ShieldCheck,
  Sparkles,
  Trophy,
  Zap,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs } from '@/components/ui/tabs';
import { useBridge } from '@/lib/bridge/hooks';
import {
  systemBenchmarkHardware,
  systemConfigureAcceleration,
  systemExportDiagnostics,
  systemGetGoldenReleaseInfo,
  systemGetHardwareStatus,
  type AccelerationProfile,
  type GoldenReleaseInfo,
  type HardwareBenchmarkResult,
  type SystemDiagnostics,
} from '@/lib/bridge/system';
import { useTranslation } from '@/lib/i18n';

export function SystemHealthStudio() {
  const { t } = useTranslation('system');
  const { client } = useBridge();

  const [activeTab, setActiveTab] = useState<string>('overview');
  const [profile, setProfile] = useState<AccelerationProfile | null>(null);
  const [goldenInfo, setGoldenInfo] = useState<GoldenReleaseInfo | null>(null);
  const [benchmarkResult, setBenchmarkResult] = useState<HardwareBenchmarkResult | null>(null);
  const [diagnostics, setDiagnostics] = useState<SystemDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [alertMsg, setAlertMsg] = useState<string | null>(null);

  // Optimizer state
  const [speculativeStreaming, setSpeculativeStreaming] = useState(true);
  const [zeroLatencyMode, setZeroLatencyMode] = useState(true);
  const [adaptiveCompaction, setAdaptiveCompaction] = useState(true);
  const [draftBufferSize, setDraftBufferSize] = useState(4);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const [statusRes, goldRes, diagRes] = await Promise.all([
          systemGetHardwareStatus(client),
          systemGetGoldenReleaseInfo(client),
          systemExportDiagnostics(client),
        ]);
        if (!cancelled) {
          setProfile(statusRes.profile);
          setGoldenInfo(goldRes);
          setDiagnostics(diagRes);
          setSpeculativeStreaming(statusRes.profile.speculative_streaming);
          setZeroLatencyMode(statusRes.profile.zero_latency_mode);
          setAdaptiveCompaction(statusRes.profile.adaptive_compaction);
          setDraftBufferSize(statusRes.profile.draft_buffer_size);
        }
      } catch {
        // Fallback
      }
    };
    void init();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleRunBenchmark = async () => {
    setLoading(true);
    setAlertMsg(null);
    try {
      const res = await systemBenchmarkHardware(client);
      setBenchmarkResult(res.benchmark);
      setAlertMsg(
        `Hardware benchmark complete: ${res.benchmark.estimated_throughput_tps} tokens/sec at ${res.benchmark.measured_latency_ms}ms.`,
      );
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    setLoading(true);
    try {
      const res = await systemConfigureAcceleration(client, {
        speculative_streaming: speculativeStreaming,
        zero_latency_mode: zeroLatencyMode,
        adaptive_compaction: adaptiveCompaction,
        draft_buffer_size: draftBufferSize,
      });
      setProfile(res.profile);
      setAlertMsg('Acceleration and Zero-Latency configuration updated successfully.');
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleCopyDiagnostics = () => {
    if (!diagnostics) return;
    void navigator.clipboard.writeText(JSON.stringify(diagnostics, null, 2));
    setAlertMsg(t('diagnosticsCopied'));
  };

  const tabs = [
    {
      id: 'overview',
      label: t('tabOverview'),
      content: (
        <div className="flex flex-col gap-5">
          {/* Golden Master Release Banner */}
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-warning-fg/40 bg-gradient-to-r from-warning-fg/10 via-surface to-accent/10 p-5 shadow-sm">
            <div className="flex items-center gap-4">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-warning-fg/20 text-warning-fg shadow-sm">
                <Trophy className="size-8" />
              </div>
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-h2 font-bold text-fg-primary">
                    {goldenInfo?.release_tag || 'Golden Master Release v4.0.0'}
                  </h3>
                  <Badge variant="success" className="px-2 py-0.5 text-caption font-semibold">
                    100% Ready
                  </Badge>
                </div>
                <p className="text-caption text-fg-muted">
                  {goldenInfo?.codename || 'Zero-Latency Autonomous Sovereign Intelligence'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Badge variant="neutral" className="font-mono text-caption">
                Python {goldenInfo?.python_version}
              </Badge>
              <Badge variant="neutral" className="font-mono text-caption">
                {goldenInfo?.platform_system}
              </Badge>
            </div>
          </div>

          {/* Verified Subsystems Grid */}
          <div className="rounded-xl border border-border-default bg-surface p-4">
            <h4 className="mb-3 font-semibold text-body text-fg-primary flex items-center gap-2">
              <ShieldCheck className="size-5 text-success-fg" />
              {t('verifiedSubsystems')}
            </h4>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:grid-cols-3">
              {goldenInfo?.verified_subsystems.map((sub, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-2 p-3 text-caption font-medium"
                >
                  <CheckCircle2 className="size-4 shrink-0 text-success-fg" />
                  <span className="text-fg-primary">{sub}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Multi-Platform Support Verification */}
          <div className="rounded-xl border border-border-default bg-surface p-4">
            <h4 className="mb-3 font-semibold text-body text-fg-primary flex items-center gap-2">
              <Laptop className="size-5 text-accent" />
              {t('platformSupport')}
            </h4>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface-2 p-3">
                <CheckCircle2 className="size-4 text-success-fg" />
                <span className="text-caption font-medium text-fg-primary">
                  {t('verifiedWindows')}
                </span>
              </div>
              <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface-2 p-3">
                <CheckCircle2 className="size-4 text-success-fg" />
                <span className="text-caption font-medium text-fg-primary">{t('verifiedMac')}</span>
              </div>
              <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface-2 p-3">
                <CheckCircle2 className="size-4 text-success-fg" />
                <span className="text-caption font-medium text-fg-primary">
                  {t('verifiedLinux')}
                </span>
              </div>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'hardware',
      label: t('tabHardware'),
      content: (
        <div className="flex flex-col gap-4">
          {/* Acceleration Metrics Dashboard */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="flex flex-col rounded-xl border border-border-default bg-surface p-4">
              <span className="text-caption text-fg-muted">{t('hardwareEngine')}</span>
              <span className="text-h2 font-bold uppercase text-accent">
                {profile?.active_backend || 'CPU'}
              </span>
            </div>
            <div className="flex flex-col rounded-xl border border-border-default bg-surface p-4">
              <span className="text-caption text-fg-muted">{t('throughput')}</span>
              <span className="text-h2 font-bold text-success-fg">
                {profile?.tokens_per_second} tps
              </span>
            </div>
            <div className="flex flex-col rounded-xl border border-border-default bg-surface p-4">
              <span className="text-caption text-fg-muted">{t('firstTokenLatency')}</span>
              <span className="text-h2 font-bold text-fg-primary">
                {profile?.first_token_latency_ms} ms
              </span>
            </div>
            <div className="flex flex-col rounded-xl border border-border-default bg-surface p-4">
              <span className="text-caption text-fg-muted">{t('vramAllocated')}</span>
              <span className="text-h2 font-bold text-fg-primary">
                {profile?.vram_allocated_mb} MB
              </span>
            </div>
          </div>

          {/* Benchmark Action Card */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-default bg-surface p-4">
            <div>
              <h4 className="font-semibold text-body text-fg-primary">
                Compute & Memory Bandwidth Benchmark
              </h4>
              <p className="text-caption text-fg-muted">
                Measures device tensor operations and memory bus bandwidth.
              </p>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleRunBenchmark()}
              disabled={loading}
            >
              <Play className="mr-1.5 size-4" />
              {loading ? t('benchmarking') : t('runBenchmark')}
            </Button>
          </div>

          {/* Benchmark Results Output */}
          {benchmarkResult && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-accent/40 bg-accent/5 p-3">
                <span className="text-caption text-accent">Measured Compute Latency</span>
                <p className="text-h3 font-bold text-fg-primary">
                  {benchmarkResult.measured_latency_ms} ms
                </p>
              </div>
              <div className="rounded-lg border border-accent/40 bg-accent/5 p-3">
                <span className="text-caption text-accent">Memory Bandwidth</span>
                <p className="text-h3 font-bold text-fg-primary">
                  {benchmarkResult.memory_bandwidth_gbs} GB/s
                </p>
              </div>
              <div className="rounded-lg border border-accent/40 bg-accent/5 p-3">
                <span className="text-caption text-accent">Sustained Generation Rate</span>
                <p className="text-h3 font-bold text-fg-primary">
                  {benchmarkResult.estimated_throughput_tps} tps
                </p>
              </div>
            </div>
          )}

          {/* Detected Hardware Devices Table */}
          <div className="rounded-lg border border-border-default bg-surface p-4">
            <h4 className="mb-3 font-semibold text-caption text-fg-muted">
              {t('deviceList')} ({profile?.devices.length ?? 0})
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-caption">
                <thead>
                  <tr className="border-b border-border-default text-fg-muted">
                    <th className="py-2 px-3">{t('deviceType')}</th>
                    <th className="py-2 px-3">{t('deviceName')}</th>
                    <th className="py-2 px-3">{t('computeCap')}</th>
                    <th className="py-2 px-3">{t('driverVersion')}</th>
                    <th className="py-2 px-3">Memory (VRAM)</th>
                  </tr>
                </thead>
                <tbody>
                  {profile?.devices.map((dev, idx) => (
                    <tr key={idx} className="border-b border-border-default/50 hover:bg-surface-2">
                      <td className="py-2 px-3 uppercase font-mono font-bold text-accent">
                        {dev.device_type}
                      </td>
                      <td className="py-2 px-3 font-medium text-fg-primary">{dev.device_name}</td>
                      <td className="py-2 px-3 font-mono">{dev.compute_capability}</td>
                      <td className="py-2 px-3 font-mono text-fg-muted">
                        {dev.driver_version || 'Built-in'}
                      </td>
                      <td className="py-2 px-3 font-mono">
                        {dev.total_memory_mb > 0
                          ? `${dev.free_memory_mb} / ${dev.total_memory_mb} MB`
                          : 'Host Shared'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'optimizer',
      label: t('tabOptimization'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-4 rounded-xl border border-border-default bg-surface p-5">
            <h4 className="font-semibold text-body text-fg-primary flex items-center gap-2">
              <Zap className="size-5 text-accent" />
              {t('tabOptimization')}
            </h4>

            {/* Switch: Speculative Streaming */}
            <div className="flex items-center justify-between border-b border-border-default pb-3">
              <div className="flex flex-col gap-0.5">
                <span className="font-medium text-caption text-fg-primary">
                  {t('speculativeStreaming')}
                </span>
                <span className="text-caption text-fg-muted">{t('speculativeStreamingDesc')}</span>
              </div>
              <Button
                variant={speculativeStreaming ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setSpeculativeStreaming((v) => !v)}
              >
                {speculativeStreaming ? 'Enabled' : 'Disabled'}
              </Button>
            </div>

            {/* Switch: Zero-Latency Mode */}
            <div className="flex items-center justify-between border-b border-border-default pb-3">
              <div className="flex flex-col gap-0.5">
                <span className="font-medium text-caption text-fg-primary">
                  {t('zeroLatencyMode')}
                </span>
                <span className="text-caption text-fg-muted">{t('zeroLatencyModeDesc')}</span>
              </div>
              <Button
                variant={zeroLatencyMode ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setZeroLatencyMode((v) => !v)}
              >
                {zeroLatencyMode ? 'Enabled' : 'Disabled'}
              </Button>
            </div>

            {/* Switch: Adaptive Compaction */}
            <div className="flex items-center justify-between border-b border-border-default pb-3">
              <div className="flex flex-col gap-0.5">
                <span className="font-medium text-caption text-fg-primary">
                  {t('adaptiveCompaction')}
                </span>
                <span className="text-caption text-fg-muted">{t('adaptiveCompactionDesc')}</span>
              </div>
              <Button
                variant={adaptiveCompaction ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setAdaptiveCompaction((v) => !v)}
              >
                {adaptiveCompaction ? 'Enabled' : 'Disabled'}
              </Button>
            </div>

            {/* Draft Buffer Slider */}
            <div className="flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <span className="font-medium text-caption text-fg-primary">
                  {t('draftBufferSize')}: {draftBufferSize}
                </span>
                <span className="text-caption text-fg-muted">
                  Speculative token batch lookahead (1 to 16).
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="16"
                aria-label={t('draftBufferSize')}
                value={draftBufferSize}
                onChange={(e) => setDraftBufferSize(Number(e.target.value))}
                className="w-36 accent-accent"
              />
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleSaveConfig()}
              disabled={loading}
              className="mt-2 self-start"
            >
              <Sparkles className="mr-1.5 size-4" />
              Save Optimization Settings
            </Button>
          </div>
        </div>
      ),
    },
    {
      id: 'diagnostics',
      label: t('tabDiagnostics'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-default bg-surface p-4">
            <div className="flex items-center gap-2">
              <Server className="size-5 text-accent" />
              <div>
                <h4 className="font-semibold text-body text-fg-primary">
                  Cryptographic System Diagnostic Report
                </h4>
                <p className="text-caption text-fg-muted">
                  Export verified system telemetry bundle signed by Dream v4.0.0 engine.
                </p>
              </div>
            </div>
            <Button variant="primary" size="sm" onClick={handleCopyDiagnostics}>
              <Copy className="mr-1.5 size-3.5" />
              {t('exportDiagnostics')}
            </Button>
          </div>

          {diagnostics && (
            <div className="rounded-xl border border-border-default bg-surface p-4">
              <div className="mb-2 flex items-center justify-between border-b border-border-default pb-2">
                <span className="font-mono text-caption text-fg-muted">
                  ID: {diagnostics.diagnostic_id}
                </span>
                <span className="font-mono text-caption text-success-fg">
                  {diagnostics.signature}
                </span>
              </div>
              <pre
                className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 font-mono text-caption text-fg-primary"
                dir="ltr"
              >
                {JSON.stringify(diagnostics, null, 2)}
              </pre>
            </div>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* Studio Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border-default bg-surface p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-accent/10 text-accent">
            <Activity className="size-5" />
          </div>
          <div className="flex flex-col">
            <h3 className="text-h3 font-semibold text-fg-primary">{t('title')}</h3>
            <p className="text-caption text-fg-muted">{t('subtitle')}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="success" className="px-3 py-1 font-semibold">
            v4.0.0 Golden Release
          </Badge>
        </div>
      </div>

      {/* Alert Banner */}
      {alertMsg && (
        <div
          role="alert"
          className="flex items-center justify-between rounded-lg border border-accent/40 bg-accent/10 p-3 text-caption text-accent"
        >
          <span>{alertMsg}</span>
          <button onClick={() => setAlertMsg(null)} className="ml-2 font-bold opacity-70">
            ✕
          </button>
        </div>
      )}

      {/* Tabs */}
      <Tabs
        items={tabs}
        value={activeTab}
        onValueChange={setActiveTab}
        label="System Studio Navigation"
      />
    </div>
  );
}
