import { VirtualList } from '@/components/shared/virtual-list';
import type { BridgeLogEntry } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';
import { formatClock } from '@/utils/format';

const LEVEL_CLASS: Record<string, string> = {
  error: 'text-danger-fg',
  warning: 'text-warning-fg',
  info: 'text-fg-secondary',
};

/** Tail-following, bounded renderer for long-running subagent output. */
export function SubagentLogTail({ log }: { log: readonly BridgeLogEntry[] }) {
  const { t } = useTranslation('subagents');
  if (log.length === 0) {
    return (
      <p className="ltr-island min-h-24 rounded-lg border border-border-default bg-sunken p-4 font-mono text-micro text-fg-muted">
        {t('waitingLog')}
      </p>
    );
  }

  return (
    <VirtualList
      items={log}
      getKey={(entry, index) => `${entry.ts}-${index}`}
      estimateSize={24}
      ariaLabel={t('activityLog')}
      followOutput
      className="ltr-island max-h-56 min-h-24 rounded-lg border border-border-default bg-sunken p-2 font-mono text-micro"
      renderItem={(entry) => (
        <div className="flex gap-2 px-1 py-0.5">
          <span className="tabular shrink-0 text-fg-muted">{formatClock(entry.ts)}</span>
          <span
            className={cn('min-w-0 break-words', LEVEL_CLASS[entry.level] ?? 'text-fg-primary')}
          >
            {entry.message}
          </span>
        </div>
      )}
    />
  );
}
