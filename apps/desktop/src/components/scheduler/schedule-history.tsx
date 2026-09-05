import { VirtualList } from '@/components/shared/virtual-list';
import { Badge } from '@/components/ui/badge';
import type { BridgeScheduleRun } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { absoluteTime } from '@/utils/time';

/** i18n key for one history-row status. */
function runStatusKey(status: string): string {
  switch (status) {
    case 'success':
      return 'statusSuccess';
    case 'error':
      return 'statusError';
    case 'approval_denied':
      return 'statusDenied';
    default:
      return 'statusRunning';
  }
}

/** Formats execution duration in seconds or milliseconds. */
function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(1)}s`;
}

/** Bounded timeline used even when a schedule has thousands of historical runs. */
export function ScheduleHistory({ runs }: { runs: readonly BridgeScheduleRun[] }) {
  const { t } = useTranslation('scheduler');
  if (runs.length === 0) return <p className="text-caption text-fg-muted">{t('historyEmpty')}</p>;

  return (
    <VirtualList
      items={runs}
      getKey={(run) => run.id}
      estimateSize={36}
      ariaLabel={t('historyTitle')}
      className="max-h-64"
      renderItem={(run) => (
        <div className="flex h-full items-center gap-2 text-caption">
          <Badge
            variant={
              run.status === 'success' ? 'success' : run.status === 'running' ? 'info' : 'danger'
            }
          >
            {t(runStatusKey(run.status))}
          </Badge>
          <span className="text-fg-muted">{absoluteTime(run.started_at)}</span>
          {run.duration !== null && run.duration !== undefined && (
            <span className="font-mono text-micro text-fg-muted">
              ({formatDuration(run.duration)})
            </span>
          )}
          <span className="min-w-0 flex-1 truncate" dir="auto">
            {run.result_summary}
          </span>
        </div>
      )}
    />
  );
}
