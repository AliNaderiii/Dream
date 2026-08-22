/**
 * Token-sized status bar: agent status, provider reachability, workspace, language,
 * sandbox, browser, and gateway indicators.
 */

import { Circle, Globe, HardDrive, Languages } from 'lucide-react';

import { BridgeStatusIndicator } from '@/components/bridge/bridge-status';
import { SandboxStatusIndicator } from '@/components/sandbox/sandbox-status';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { LANGUAGES, useTranslation } from '@/lib/i18n';
import { useAppStore } from '@/stores/use-app-store';
import { useProviderStore } from '@/stores/use-provider-store';
import type { AgentStatus } from '@/types';
import { cn } from '@/utils/cn';

/** Maps agent status to a dot colour and label key. */
const STATUS_META: Record<AgentStatus, { labelKey: string; className: string }> = {
  idle: { labelKey: 'status.idle', className: 'text-fg-muted' },
  running: { labelKey: 'status.running', className: 'text-success-fg' },
  paused: { labelKey: 'status.paused', className: 'text-warning-fg' },
  error: { labelKey: 'status.error', className: 'text-danger-fg' },
  offline: { labelKey: 'status.offline', className: 'text-fg-muted' },
};

export function StatusBar() {
  const { t } = useTranslation('common');
  const { t: ts } = useTranslation('settings');
  const agentStatus = useAppStore((s) => s.agentStatus);
  const workspaceRoot = useAppStore((s) => s.workspaceRoot);
  const locale = useAppStore((s) => s.locale);
  const setLocale = useAppStore((s) => s.setLocale);

  const providers = useProviderStore((s) => s.providers);
  const activeProviderId = useProviderStore((s) => s.activeProviderId);
  const activeProvider = providers.find((p) => p.id === activeProviderId);

  const status = STATUS_META[agentStatus];
  const activeLanguage = LANGUAGES.find((l) => l.code === locale);

  return (
    <footer className="flex h-6 shrink-0 items-center gap-3 border-t border-border-default bg-surface-raised px-3 text-caption text-fg-secondary">
      {agentStatus === 'running' && (
        <span className="activity-travel h-0.5 w-8 rounded-full bg-surface-2" aria-hidden />
      )}
      <span className="flex items-center gap-1.5">
        <Circle className={cn('size-2 fill-current', status.className)} aria-hidden />
        <span>{t(status.labelKey)}</span>
      </span>

      <BridgeStatusIndicator />

      <SandboxStatusIndicator />

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
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 rounded-xs hover:text-fg-primary"
              aria-label={ts('language')}
            >
              <Languages className="size-3" aria-hidden />
              <span>{activeLanguage?.flag}</span>
              {t(activeLanguage?.nameKey ?? 'language.en')}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {LANGUAGES.map((lang) => (
              <DropdownMenuItem
                key={lang.code}
                onSelect={() => setLocale(lang.code)}
                className={locale === lang.code ? 'bg-accent-soft text-accent-text' : ''}
              >
                <span className="me-2">{lang.flag}</span>
                {t(lang.nameKey)}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </span>
    </footer>
  );
}
