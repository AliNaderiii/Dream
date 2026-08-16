/**
 * Connectivity screen (Prompt P-07): six platform cards, per-platform
 * configure forms, link codes, and the message log — all through the
 * `gateway.*` bridge methods. In `npm run dev` the echo transport answers
 * the same calls, so the screen is browsable with no sidecar running.
 */

import { LoaderCircle, Play, Radio, Square } from 'lucide-react';
import { useEffect, useState } from 'react';

import { MessageLog } from '@/components/connectivity/message-log';
import { PlatformCard } from '@/components/connectivity/platform-card';
import { PlatformConfig } from '@/components/connectivity/platform-config';
import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { GatewayPlatformName } from '@/lib/bridge/types';
import { useConnectivityStore } from '@/stores/use-connectivity-store';

export function ConnectivityRoute() {
  const platforms = useConnectivityStore((state) => state.platforms);
  const status = useConnectivityStore((state) => state.status);
  const logs = useConnectivityStore((state) => state.logs);
  const linkCodes = useConnectivityStore((state) => state.linkCodes);
  const expandedPlatform = useConnectivityStore((state) => state.expandedPlatform);
  const loading = useConnectivityStore((state) => state.loading);
  const error = useConnectivityStore((state) => state.error);
  const load = useConnectivityStore((state) => state.load);
  const startGateway = useConnectivityStore((state) => state.startGateway);
  const stopGateway = useConnectivityStore((state) => state.stopGateway);
  const configure = useConnectivityStore((state) => state.configure);
  const fetchLogs = useConnectivityStore((state) => state.fetchLogs);
  const issueLinkCode = useConnectivityStore((state) => state.issueLinkCode);
  const setExpandedPlatform = useConnectivityStore((state) => state.setExpandedPlatform);
  const [logPlatform, setLogPlatform] = useState<GatewayPlatformName | null>(null);

  useEffect(() => {
    void load();
    void fetchLogs(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const running = status?.running ?? false;

  const selectLogPlatform = (platform: GatewayPlatformName | null) => {
    setLogPlatform(platform);
    void fetchLogs(platform);
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Radio className="size-6 text-fg-secondary" aria-hidden />
          <div>
            <h1 className="text-h2 font-semibold">Connectivity</h1>
            <p className="text-body text-fg-secondary">
              Talk to Dream from Telegram, Discord, Slack, WhatsApp, Signal, and Email.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={running ? 'success' : 'neutral'}>
            {running ? 'Gateway running' : 'Gateway stopped'}
          </Badge>
          {running ? (
            <Button variant="secondary" onClick={() => void stopGateway()}>
              <Square className="size-4" aria-hidden />
              Stop
            </Button>
          ) : (
            <Button variant="primary" onClick={() => void startGateway()}>
              <Play className="size-4" aria-hidden />
              Start
            </Button>
          )}
        </div>
      </header>

      {error && (
        <p className="rounded-md bg-danger-bg px-3 py-2 text-body text-danger-fg" role="alert">
          {error}
        </p>
      )}

      {loading && platforms.length === 0 ? (
        <div className="flex h-full items-center justify-center text-fg-muted">
          <LoaderCircle className="size-6 animate-spin" aria-hidden />
          <span className="ms-2 text-body">Loading platforms…</span>
        </div>
      ) : platforms.length === 0 ? (
        <EmptyState
          icon={Radio}
          title="No platforms available"
          description="The sidecar did not report a platform catalog. Start the gateway to retry."
          action={{ label: 'Retry', onClick: () => void load() }}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {platforms.map((platform) => {
              const adapterStatus = status?.adapters.find(
                (adapter) => adapter.platform === platform.name,
              );
              const expanded = expandedPlatform === platform.name;
              return (
                <div key={platform.name} className="flex flex-col gap-0">
                  <PlatformCard
                    platform={platform}
                    status={adapterStatus}
                    expanded={expanded}
                    linkCode={linkCodes[platform.name]}
                    onToggleEnabled={(target, enabled) => void configure(target.name, { enabled })}
                    onToggleExpanded={() => setExpandedPlatform(expanded ? null : platform.name)}
                    onIssueLinkCode={() => void issueLinkCode(platform.name)}
                  />
                  {expanded && (
                    <div className="rounded-b-lg border border-t-0 border-accent bg-surface px-4 pb-4 pt-0">
                      <PlatformConfig
                        platform={platform}
                        onSave={(config) => void configure(platform.name, config)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <MessageLog
            platforms={platforms}
            logs={logs}
            selectedPlatform={logPlatform}
            onSelectPlatform={selectLogPlatform}
            onRefresh={() => selectLogPlatform(logPlatform)}
          />
        </>
      )}
    </div>
  );
}
