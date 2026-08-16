/**
 * Sandbox configuration UI — Docker sandbox settings and status.
 *
 * Allows enabling/disabling the sandbox, configuring default resource limits,
 * and showing the Docker daemon status.
 */

import { Container, FlaskConical, Loader2, Terminal } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import type { SandboxStatus } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

/** Resource limits editable by the user. */
interface EditableLimits {
  cpuCount: number;
  memoryMb: number;
  timeoutSeconds: number;
  networkEnabled: boolean;
}

export function SandboxSettings() {
  const { call } = useBridge();
  const [status, setStatus] = useState<SandboxStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sandboxEnabled, setSandboxEnabled] = useState(true);
  const [limits, setLimits] = useState<EditableLimits>({
    cpuCount: 1,
    memoryMb: 2048,
    timeoutSeconds: 60,
    networkEnabled: false,
  });

  const checkStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await call<SandboxStatus>('sandbox.status');
      setStatus(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to check sandbox status');
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [call]);

  useEffect(() => {
    let ignore = false;
    const run = async () => {
      if (!sandboxEnabled) return;
      setLoading(true);
      setError(null);
      try {
        const result = await call<SandboxStatus>('sandbox.status');
        if (!ignore) setStatus(result);
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to check sandbox status');
          setStatus(null);
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    };
    void run();
    return () => {
      ignore = true;
    };
  }, [sandboxEnabled, call]);

  const isAvailable = status?.available === true;

  return (
    <section>
      <h2 className="pb-2 text-h2 font-semibold">Docker Sandbox</h2>

      <div className="flex items-center justify-between border-b border-border-default py-3">
        <div>
          <p className="text-body font-medium">Enable Docker sandbox</p>
          <p className="text-caption text-fg-secondary">
            Isolated code execution for Python, R, and shell scripts
          </p>
        </div>
        <Button
          size="sm"
          variant={sandboxEnabled ? 'primary' : 'secondary'}
          aria-pressed={sandboxEnabled}
          onClick={() => setSandboxEnabled((v) => !v)}
        >
          {sandboxEnabled ? 'On' : 'Off'}
        </Button>
      </div>

      {/* Status indicator */}
      <div className="border-b border-border-default py-3">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-body font-medium">Docker daemon</p>
          </div>
          <div className="flex items-center gap-2">
            {loading ? (
              <Loader2 className="size-4 animate-spin text-fg-muted" />
            ) : error ? (
              <span className="flex items-center gap-1 text-caption text-danger-fg">
                <span className="size-2 rounded-full bg-danger-fg" />
                Error
              </span>
            ) : isAvailable ? (
              <span className="flex items-center gap-1 text-caption text-success-fg">
                <span className="size-2 rounded-full bg-success-fg" />
                Available
              </span>
            ) : (
              <span className="flex items-center gap-1 text-caption text-fg-muted">
                <span className="size-2 rounded-full bg-fg-muted" />
                Unavailable
              </span>
            )}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                void checkStatus();
              }}
              disabled={loading}
            >
              Refresh
            </Button>
          </div>
        </div>

        {/* Images status */}
        {status?.images_available && Object.keys(status.images_available).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(status.images_available).map(([lang, available]) => (
              <span
                key={lang}
                className={cn(
                  'inline-flex items-center gap-1 rounded-xs px-2 py-0.5 text-caption',
                  available ? 'bg-surface-raised text-fg-primary' : 'bg-surface text-fg-muted',
                )}
              >
                {lang === 'python' ? (
                  <Terminal className="size-3" />
                ) : lang === 'r' ? (
                  <FlaskConical className="size-3" />
                ) : (
                  <Container className="size-3" />
                )}
                {lang}
                {available ? ' ✓' : ' —'}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Resource limits config */}
      {sandboxEnabled && (
        <>
          <div className="border-b border-border-default py-3">
            <p className="text-body font-medium mb-2">Default resource limits</p>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-caption text-fg-secondary">CPU cores</span>
                <input
                  type="number"
                  min={0.25}
                  max={8}
                  step={0.25}
                  value={limits.cpuCount}
                  onChange={(e) =>
                    setLimits((l) => ({ ...l, cpuCount: parseFloat(e.target.value) || 1 }))
                  }
                  className="w-full rounded-xs border border-border-default bg-surface px-2 py-1 text-body"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-caption text-fg-secondary">Memory (MB)</span>
                <input
                  type="number"
                  min={128}
                  max={16384}
                  step={128}
                  value={limits.memoryMb}
                  onChange={(e) =>
                    setLimits((l) => ({ ...l, memoryMb: parseInt(e.target.value) || 2048 }))
                  }
                  className="w-full rounded-xs border border-border-default bg-surface px-2 py-1 text-body"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-caption text-fg-secondary">Timeout (seconds)</span>
                <input
                  type="number"
                  min={5}
                  max={600}
                  step={5}
                  value={limits.timeoutSeconds}
                  onChange={(e) =>
                    setLimits((l) => ({ ...l, timeoutSeconds: parseInt(e.target.value) || 60 }))
                  }
                  className="w-full rounded-xs border border-border-default bg-surface px-2 py-1 text-body"
                />
              </label>
              <label className="flex flex-col gap-1 justify-end">
                <span className="text-caption text-fg-secondary">Network access</span>
                <button
                  type="button"
                  onClick={() => setLimits((l) => ({ ...l, networkEnabled: !l.networkEnabled }))}
                  className={cn(
                    'w-full rounded-xs border px-2 py-1 text-left text-body',
                    limits.networkEnabled
                      ? 'border-success-fg text-success-fg'
                      : 'border-border-default text-fg-muted',
                  )}
                >
                  {limits.networkEnabled ? 'Enabled' : 'Disabled'}
                </button>
              </label>
            </div>
          </div>

          {/* Quick actions */}
          <div className="py-3">
            <p className="text-caption text-fg-secondary mb-2">
              Package management is available via the agent chat. Ask the agent to install packages
              for your data science tasks.
            </p>
          </div>
        </>
      )}
    </section>
  );
}
