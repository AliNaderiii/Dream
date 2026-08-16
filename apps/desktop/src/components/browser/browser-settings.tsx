/**
 * Browser control settings UI — Chrome attachment and status.
 *
 * Manages attaching to the user's Chrome or launching an isolated instance.
 * Shows the browser connection status and approved domains.
 */

import { Globe, GlobeLock, Monitor, Unplug } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import type { BrowserStatus } from '@/lib/bridge/types';

export function BrowserSettings() {
  const { call } = useBridge();
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attachPort, setAttachPort] = useState(9222);
  const [browserEnabled, setBrowserEnabled] = useState(true);

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await call<BrowserStatus>('browser.status');
      setStatus(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to check browser status');
    } finally {
      setLoading(false);
    }
  }, [call]);

  useEffect(() => {
    if (browserEnabled) void refreshStatus();
  }, [browserEnabled, refreshStatus]);

  const handleAttach = async () => {
    setLoading(true);
    setError(null);
    try {
      await call<{ mode: string; port: number }>('browser.attach', {
        port: attachPort,
      });
      setStatus((prev) =>
        prev
          ? { ...prev, attached: true, attached_to_existing: true, has_page: true }
          : { attached: true, attached_to_existing: true, has_page: true, pending_approvals: 0, approved_domains: [], current_session: null, screenshot_dir: '' },
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to attach Chrome');
    } finally {
      setLoading(false);
    }
  };

  const handleLaunchIsolated = async () => {
    setLoading(true);
    setError(null);
    try {
      await call<{ mode: string }>('browser.launch_isolated');
      setStatus((prev) =>
        prev
          ? { ...prev, attached: true, attached_to_existing: false, has_page: true }
          : { attached: true, attached_to_existing: false, has_page: true, pending_approvals: 0, approved_domains: [], current_session: null, screenshot_dir: '' },
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to launch Chrome');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = async () => {
    setLoading(true);
    try {
      await call('browser.close');
      setStatus(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to close browser');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section>
      <h2 className="pb-2 text-h2 font-semibold">Browser Control</h2>

      <div className="flex items-center justify-between border-b border-border-default py-3">
        <div>
          <p className="text-body font-medium">Enable browser control</p>
          <p className="text-caption text-fg-secondary">
            Let the agent drive your Chrome browser to interact with websites
          </p>
        </div>
        <Button
          size="sm"
          variant={browserEnabled ? 'primary' : 'secondary'}
          aria-pressed={browserEnabled}
          onClick={() => setBrowserEnabled((v) => !v)}
        >
          {browserEnabled ? 'On' : 'Off'}
        </Button>
      </div>

      {/* Status indicator */}
      <div className="border-b border-border-default py-3">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-body font-medium">Browser status</p>
          </div>
          <div className="flex items-center gap-2">
            {status?.attached ? (
              <>
                <span className="flex items-center gap-1 text-caption text-success-fg">
                  <Monitor className="size-3" />
                  {status.attached_to_existing ? 'Attached' : 'Isolated'}
                </span>
                <span className="text-caption text-fg-muted">
                  ({status.has_page ? 'page active' : 'no page'})
                </span>
              </>
            ) : (
              <span className="flex items-center gap-1 text-caption text-fg-muted">
                <Unplug className="size-3" />
                No browser attached
              </span>
            )}
          </div>
        </div>

        {/* Approved domains */}
        {status?.approved_domains && status.approved_domains.length > 0 && (
          <div className="mt-2">
            <p className="text-caption text-fg-secondary mb-1">Approved domains:</p>
            <div className="flex flex-wrap gap-1">
              {status.approved_domains.map((domain) => (
                <span
                  key={domain}
                  className="inline-flex items-center gap-1 rounded-xs bg-surface-raised px-2 py-0.5 text-caption"
                >
                  <GlobeLock className="size-3" />
                  {domain}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Connection controls */}
      {browserEnabled && (
        <div className="border-b border-border-default py-3">
          <p className="text-body font-medium mb-2">Connection</p>

          {!status?.attached ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-2">
                  <span className="text-caption text-fg-secondary">Debug port:</span>
                  <input
                    type="number"
                    min={9222}
                    max={9999}
                    value={attachPort}
                    onChange={(e) => setAttachPort(parseInt(e.target.value) || 9222)}
                    className="w-20 rounded-xs border border-border-default bg-surface px-2 py-1 text-body"
                  />
                </label>
                <Button size="sm" onClick={handleAttach} disabled={loading}>
                  {loading ? 'Connecting…' : 'Attach to Chrome'}
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-caption text-fg-secondary">
                  Or start a fresh, isolated instance:
                </span>
                <Button size="sm" variant="secondary" onClick={handleLaunchIsolated} disabled={loading}>
                  {loading ? 'Launching…' : 'Launch Isolated'}
                </Button>
              </div>
              {error && <p className="text-caption text-danger-fg">{error}</p>}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-caption text-fg-secondary">
                Browser is {status.attached_to_existing ? 'attached to your Chrome' : 'running in isolated mode'}.
              </span>
              <Button size="sm" variant="secondary" onClick={handleClose} disabled={loading}>
                Close Browser
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Security info */}
      <div className="py-3">
        <div className="rounded-xs bg-surface-raised p-3 text-caption text-fg-secondary">
          <p className="flex items-center gap-1 font-medium text-fg-primary">
            <Globe className="size-3" /> Security &amp; Privacy
          </p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            <li>Each browser session requires your explicit approval</li>
            <li>Your real Chrome profile is never copied or transmitted</li>
            <li>Screenshots are saved locally only</li>
            <li>Sessions time out after 5 minutes</li>
          </ul>
        </div>
      </div>
    </section>
  );
}