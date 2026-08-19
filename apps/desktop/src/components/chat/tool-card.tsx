/**
 * Tool card rendered inside the conversation transcript (S07).
 *
 * Each tool call in a turn appears as a compact card showing:
 *   - tool name
 *   - arguments summary
 *   - status: ok | error | blocked | pending
 *   - result excerpt (when status is ok)
 *
 * RTL-safe: the card uses `start`/`end` logical properties.
 */

import { AlertTriangle, CheckCircle, Loader2, ShieldAlert, XCircle } from 'lucide-react';

import type { ToolCardEntry } from '@/types';
import { cn } from '@/utils/cn';

const STATUS_CONFIG: Record<
  ToolCardEntry['status'],
  { icon: typeof CheckCircle; label: string; colorClass: string; bgClass: string }
> = {
  pending: {
    icon: Loader2,
    label: 'Running…',
    colorClass: 'text-fg-muted',
    bgClass: 'bg-surface-2',
  },
  ok: {
    icon: CheckCircle,
    label: 'OK',
    colorClass: 'text-success-fg',
    bgClass: 'bg-success-bg',
  },
  error: {
    icon: XCircle,
    label: 'Error',
    colorClass: 'text-danger-fg',
    bgClass: 'bg-danger-bg',
  },
  blocked: {
    icon: ShieldAlert,
    label: 'Blocked',
    colorClass: 'text-warning-fg',
    bgClass: 'bg-warning-bg',
  },
};

interface ToolCardProps {
  card: ToolCardEntry;
}

export function ToolCard({ card }: ToolCardProps) {
  const config = STATUS_CONFIG[card.status];
  const Icon = config.icon;

  return (
    <div
      role="status"
      aria-label={`${card.name} — ${config.label}`}
      className={cn(
        'my-1 flex items-start gap-2 rounded-md border border-border-default px-3 py-2 text-caption',
        config.bgClass,
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 size-4 shrink-0',
          config.colorClass,
          card.status === 'pending' && 'animate-spin',
        )}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-fg-primary">{card.name}</span>
          <span className={cn('rounded-xs px-1 text-micro', config.colorClass)}>
            {config.label}
          </span>
        </div>
        {card.argsSummary && (
          <p className="mt-0.5 truncate text-micro text-fg-muted">{card.argsSummary}</p>
        )}
        {card.status === 'ok' && card.resultExcerpt && (
          <p className="mt-1 line-clamp-2 text-micro text-fg-secondary">{card.resultExcerpt}</p>
        )}
        {card.status === 'blocked' && (
          <p className="mt-1 text-micro text-warning-fg">
            <AlertTriangle className="me-1 inline-block size-3" aria-hidden />
            Waiting for approval…
          </p>
        )}
      </div>
    </div>
  );
}
