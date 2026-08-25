/**
 * List of past research sessions with status cards.
 */

import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Microscope,
  PauseCircle,
  XCircle,
} from 'lucide-react';
import type { ComponentType } from 'react';

import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/shared/empty-state';
import { useTranslation } from '@/lib/i18n';
import type { ResearchSession, ResearchStatus } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

interface StatusConfig {
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  variant: 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';
  ariaLabel: string;
}

const STATUS_CONFIG: Record<ResearchStatus, StatusConfig> = {
  pending: { icon: Clock, variant: 'neutral', ariaLabel: 'Pending' },
  planning: { icon: Loader2, variant: 'info', ariaLabel: 'Planning' },
  awaiting_approval: { icon: PauseCircle, variant: 'warning', ariaLabel: 'Awaiting approval' },
  running: { icon: Loader2, variant: 'accent', ariaLabel: 'Running' },
  completed: { icon: CheckCircle2, variant: 'success', ariaLabel: 'Completed' },
  failed: { icon: XCircle, variant: 'danger', ariaLabel: 'Failed' },
  cancelled: { icon: AlertCircle, variant: 'neutral', ariaLabel: 'Cancelled' },
};

function StatusBadge({ status }: { status: ResearchStatus }) {
  const { t } = useTranslation('research');
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;
  return (
    <Badge variant={config.variant}>
      <Icon
        className={cn(
          'size-3.5',
          status === 'running' && 'animate-spin motion-reduce:animate-none',
        )}
        aria-hidden
      />
      {t(`status.${status}`)}
    </Badge>
  );
}

function SessionCard({ session }: { session: ResearchSession }) {
  const { t } = useTranslation('research');
  const { setActiveSession, setView } = useResearchStore();

  const handleClick = () => {
    setActiveSession(session.session_id);
    // Route to the appropriate view based on status
    if (session.status === 'completed' && session.report) {
      setView('report');
    } else if (session.status === 'awaiting_approval' && session.plan) {
      setView('plan');
    } else if (session.status === 'running' || session.status === 'planning') {
      setView('trace');
    } else {
      setView('trace'); // Default to trace for visibility
    }
  };

  const sections = session.plan?.outline.length ?? 0;
  const verdict = session.report?.claims.length ?? 0;

  return (
    <button
      type="button"
      onClick={handleClick}
      className="flex w-full flex-col gap-2 rounded-lg border border-border-default bg-surface p-4 text-start transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      aria-label={t('openSession', { topic: session.topic })}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-body font-semibold">{session.topic}</h3>
          <p className="mt-0.5 line-clamp-2 text-caption text-fg-muted">{session.objective}</p>
        </div>
        <StatusBadge status={session.status} />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-micro text-fg-muted">
        <span>{new Date(session.created_at).toLocaleDateString()}</span>
        {sections > 0 && <span>{t('sections', { count: sections })}</span>}
        {verdict > 0 && <span>{t('claims', { count: verdict })}</span>}
        <span className="truncate">{session.model_route}</span>
      </div>

      {session.error && (
        <p className="mt-1 rounded bg-danger-bg px-2 py-1 text-micro text-danger-fg">
          {session.error}
        </p>
      )}
    </button>
  );
}

export function ResearchSessionList() {
  const { t } = useTranslation('research');
  const sessions = useResearchStore((s) => s.sessions);

  if (sessions.length === 0) {
    return (
      <EmptyState icon={Microscope} title={t('noSessions')} description={t('noSessionsDesc')} />
    );
  }

  return (
    <ul className="flex flex-col gap-3 overflow-y-auto" role="list">
      {sessions.map((session) => (
        <li key={session.session_id}>
          <SessionCard session={session} />
        </li>
      ))}
    </ul>
  );
}
