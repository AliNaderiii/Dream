/** Expandable, localized tool-call card with calm running and settled states. */

import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  CircleEllipsis,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';

import { useTranslation } from '@/lib/i18n';
import type { ToolCardEntry } from '@/types';
import { cn } from '@/utils/cn';

const STATUS_CONFIG: Record<
  ToolCardEntry['status'],
  { icon: typeof CheckCircle; labelKey: string; colorClass: string; bgClass: string }
> = {
  pending: {
    icon: CircleEllipsis,
    labelKey: 'tool.running',
    colorClass: 'text-info-fg',
    bgClass: 'bg-info-bg',
  },
  ok: {
    icon: CheckCircle,
    labelKey: 'tool.ok',
    colorClass: 'text-success-fg',
    bgClass: 'bg-success-bg',
  },
  error: {
    icon: XCircle,
    labelKey: 'tool.error',
    colorClass: 'text-danger-fg',
    bgClass: 'bg-danger-bg',
  },
  blocked: {
    icon: ShieldAlert,
    labelKey: 'approval.blocked',
    colorClass: 'text-warning-fg',
    bgClass: 'bg-warning-bg',
  },
};

interface ToolCardProps {
  card: ToolCardEntry;
}

export function ToolCard({ card }: ToolCardProps) {
  const { t } = useTranslation('chat');
  const [expanded, setExpanded] = useState(true);
  const config = STATUS_CONFIG[card.status];
  const Icon = config.icon;
  const label = t(config.labelKey);
  const detailId = `tool-${card.id}-details`;

  return (
    <article
      aria-label={`${card.name} — ${label}`}
      className={cn(
        'my-1 overflow-hidden rounded-lg border border-border-default text-caption',
        config.bgClass,
        card.status === 'pending' && 'streaming-sweep',
      )}
    >
      <button
        type="button"
        aria-label={t(expanded ? 'tool.hideDetails' : 'tool.showDetails', { tool: card.name })}
        aria-expanded={expanded}
        aria-controls={detailId}
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-start"
      >
        <Icon className={cn('size-4 shrink-0', config.colorClass)} aria-hidden />
        <span className="min-w-0 flex-1 truncate font-medium text-fg-primary bidi-isolate">
          {card.name}
        </span>
        <span
          role="status"
          aria-live={card.status === 'pending' ? 'polite' : 'off'}
          aria-atomic="true"
          aria-label={`${card.name} — ${label}`}
          className={cn('rounded-full px-2 py-0.5 text-micro font-semibold', config.colorClass)}
        >
          {label}
        </span>
        <ChevronDown
          className={cn(
            'size-4 shrink-0 text-fg-muted transition-transform duration-normal',
            expanded && 'rotate-180',
          )}
          aria-hidden
        />
      </button>

      {expanded && (
        <div id={detailId} className="motion-enter border-t border-border-default px-3 py-2">
          {card.argsSummary && (
            <pre className="ltr-island selectable overflow-x-auto whitespace-pre-wrap text-micro text-fg-secondary">
              {card.argsSummary}
            </pre>
          )}
          {card.status === 'ok' && card.resultExcerpt && (
            <p className="selectable mt-2 line-clamp-3 text-micro text-fg-secondary" dir="auto">
              {card.resultExcerpt}
            </p>
          )}
          {card.status === 'blocked' && (
            <p className="mt-2 text-micro text-warning-fg">
              <AlertTriangle className="me-1 inline-block size-3" aria-hidden />
              {t('approval.waitingForApproval')}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
