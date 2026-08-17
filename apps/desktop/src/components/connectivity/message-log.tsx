/**
 * Message log viewer: the last 100 messages per platform.
 *
 * Rows come from `gateway.logs`. End-to-end-encrypted platforms log only the
 * fact that a message happened — the text column renders an em-dash and the
 * header explains why (gate G11: Signal content is never persisted).
 */

import { ArrowDownLeft, ArrowUpRight, Inbox, Lock } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/shared/empty-state';
import type { GatewayLogsResult, GatewayPlatform, GatewayPlatformName } from '@/lib/bridge/types';

interface MessageLogProps {
  platforms: GatewayPlatform[];
  logs: GatewayLogsResult | null;
  selectedPlatform: GatewayPlatformName | null;
  onSelectPlatform: (platform: GatewayPlatformName | null) => void;
  onRefresh: () => void;
}

function timeLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function MessageLog({
  platforms,
  logs,
  selectedPlatform,
  onSelectPlatform,
  onRefresh,
}: MessageLogProps) {
  const selected = platforms.find((platform) => platform.name === selectedPlatform);
  const isE2e = selected?.privacy === 'e2e';
  const entries = logs?.entries ?? [];

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-body-lg font-semibold">Message log</h2>
        <div className="flex flex-wrap items-center gap-1">
          <select
            value={selectedPlatform ?? ''}
            onChange={(event) =>
              onSelectPlatform((event.target.value || null) as GatewayPlatformName | null)
            }
            className="h-8 rounded-md border border-border-default bg-sunken px-2 text-body text-fg-primary focus:border-accent focus:outline-none"
            aria-label="Platform"
          >
            <option value="">All platforms</option>
            {platforms.map((platform) => (
              <option key={platform.name} value={platform.name}>
                {platform?.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={onRefresh}
            className="h-8 rounded-md border border-border-default bg-sunken px-3 text-caption font-medium text-fg-secondary hover:bg-surface-2 hover:text-fg-primary"
          >
            Refresh
          </button>
        </div>
      </div>

      {isE2e && (
        <p className="flex items-center gap-1.5 rounded-md bg-info-bg px-2 py-1 text-caption text-info-fg">
          <Lock className="size-3.5" aria-hidden />
          Signal traffic is end-to-end encrypted — the log records only that a message happened.
        </p>
      )}

      {entries.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="No messages logged"
          description="Messages routed through the gateway appear here, newest first."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-start text-body">
            <thead>
              <tr className="border-b border-border-default text-caption text-fg-muted">
                <th className="pe-2 py-1.5 text-start font-medium">Time</th>
                <th className="pe-2 py-1.5 text-start font-medium">Direction</th>
                <th className="pe-2 py-1.5 text-start font-medium">User</th>
                <th className="py-1.5 text-start font-medium">Message</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, index) => (
                <tr
                  key={`${entry.timestamp}-${index}`}
                  className="border-b border-border-default/50 align-top"
                >
                  <td className="whitespace-nowrap pe-2 py-1.5 text-micro text-fg-muted tabular">
                    {timeLabel(entry.timestamp)}
                  </td>
                  <td className="pe-2 py-1.5">
                    <Badge variant={entry.direction === 'in' ? 'neutral' : 'accent'}>
                      {entry.direction === 'in' ? (
                        <ArrowDownLeft className="size-3" aria-hidden />
                      ) : (
                        <ArrowUpRight className="size-3" aria-hidden />
                      )}
                      {entry.direction}
                    </Badge>
                  </td>
                  <td className="max-w-40 truncate pe-2 py-1.5 text-caption text-fg-secondary">
                    {entry.user_id}
                  </td>
                  <td className="py-1.5 text-body text-fg-primary">
                    {entry.text || <span className="text-fg-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
