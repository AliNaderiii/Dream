/**
 * 24px status bar: agent status, provider reachability, workspace, language.
 */

import { Circle, Globe, HardDrive, Languages } from 'lucide-react';

import { useAppStore } from '@/stores/use-app-store';
import { useProviderStore } from '@/stores/use-provider-store';
import type { AgentStatus } from '@/types';
import { cn } from '@/utils/cn';

/** Maps agent status to a dot colour and label. */
const STATUS_META: Record<AgentStatus, { label: string; className: string }> = {
  idle: { label: 'Idle', className: 'text-fg-muted' },
  running: { label: 'Running', className: 'text-success-fg' },
  paused: { label: 'Paused', className: 'text-warning-fg' },
  error: { label: 'Error', className: 'text-danger-fg' },
  offline: { label: 'Offline', className: 'text-fg-muted' },
};

export function StatusBar() {
  const agentStatus = useAppStore((s) => s.agentStatus);
  const workspaceRoot = useAppStore((s) => s.workspaceRoot);
  const locale = useAppStore((s) => s.locale);
  const setLocale = useAppStore((s) => s.setLocale);

  const providers = useProviderStore((s) => s.providers);
  const activeProviderId = useProviderStore((s) => s.activeProviderId);
  const activeProvider = providers.find((p) => p.id === activeProviderId);

  const status = STATUS_META[agentStatus];

  return (
    <footer className="flex h-6 shrink-0 items-center gap-3 border-t border-border-default bg-surface px-3 text-caption text-fg-secondary">
      <span className="flex items-center gap-1.5">
        <Circle className={cn('size-2 fill-current', status.className)} aria-hidden />
        <span>{status.label}</span>
      </span>

      {activeProvider && (
        <span className="flex items-center gap-1.5">
          {activeProvider.local ? (
            <HardDrive className="size-3" aria-hidden />
          ) : (
            <Globe className="size-3" aria-hidden />
          )}
          <span>{activeProvider.name}</span>
          {activeProvider.latencyMs !== undefined && (
            <span className="ltr-island tabular text-fg-muted">{activeProvider.latencyMs}ms</span>
          )}
        </span>
      )}

      <span className="ms-auto flex items-center gap-3">
        {workspaceRoot && (
          <span className="ltr-island max-w-72 truncate text-fg-muted" title={workspaceRoot}>
            {workspaceRoot}
          </span>
        )}
        <button
          type="button"
          onClick={() => setLocale(locale === 'fa' ? 'en' : 'fa')}
          className="flex items-center gap-1 rounded-xs hover:text-fg-primary"
          aria-label={locale === 'fa' ? 'Switch to English' : 'تغییر به فارسی'}
        >
          <Languages className="size-3" aria-hidden />
          {locale === 'fa' ? 'فارسی' : 'English'}
        </button>
      </span>
    </footer>
  );
}
