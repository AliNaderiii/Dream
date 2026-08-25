/**
 * List of past research sessions with status cards.
 */

import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Microscope,
  PauseCircle,
  PenLine,
  XCircle,
} from 'lucide-react';
import type { ComponentType } from 'react';

import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/shared/empty-state';
import { useTranslation } from '@/lib/i18n';
import { researchGet } from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import type { ListSummary, ResearchStatus } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

interface StatusConfig {
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  variant: 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';
}

const STATUS_CONFIG: Record<ResearchStatus, StatusConfig> = {
  IDLE: { icon: Clock, variant: 'neutral' },
  PLANNING: { icon: Loader2, variant: 'info' },
  APPROVAL_PENDING: { icon: PauseCircle, variant: 'warning' },
  IN_PROGRESS: { icon: Loader2, variant: 'accent' },
  PROOFREAD: { icon: PenLine, variant: 'info' },
  COMPILING: { icon: FileText, variant: 'accent' },
  COMPLETE: { icon: CheckCircle2, variant: 'success' },
  FAILED: { icon: XCircle, variant: 'danger' },
  CANCELLED: { icon: AlertCircle, variant: 'neutral' },
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
          (status === 'IN_PROGRESS' || status === 'PLANNING' || status === 'COMPILING') &&
            'animate-spin motion-reduce:animate-none',
        )}
        aria-hidden
      />
      {t(`status.${status}`)}
    </Badge>
  );
}

function SessionCard({ session }: { session: ListSummary }) {
  const { t } = useTranslation('research');
  const { client } = useBridge();
  const { setActiveSession, setActiveRecord, setView } = useResearchStore();

  const handleClick = () => {
    setActiveSession(session.session_id);
    // Fetch the full record and route to the appropriate view
    researchGet(client, session.session_id)
      .then((record) => {
        setActiveRecord(record);
        if (record.status === 'COMPLETE') {
          setView('report');
        } else if (record.status === 'APPROVAL_PENDING') {
          setView('plan');
        } else if (
          record.status === 'IN_PROGRESS' ||
          record.status === 'PLANNING' ||
          record.status === 'COMPILING' ||
          record.status === 'PROOFREAD'
        ) {
          setView('trace');
        } else if (record.status === 'IDLE') {
          setView('plan'); // Trigger planning
        } else {
          setView('trace');
        }
      })
      .catch(() => {
        setView('trace');
      });
  };

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
        </div>
        <StatusBadge status={session.status} />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-micro text-fg-muted">
        <span>{new Date(session.created_at * 1000).toLocaleDateString()}</span>
        {session.sections > 0 && <span>{t('sections', { count: session.sections })}</span>}
        {session.published && <Badge variant="success">{t('published')}</Badge>}
      </div>
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
