/**
 * Status vocabulary for subagents, rendered the same way everywhere.
 *
 * Colour is never the only signal (design-system §2.3): every badge pairs its
 * tint with an icon and a word.
 */

import {
  Ban,
  CheckCircle2,
  CircleDashed,
  Loader2,
  PauseCircle,
  TimerOff,
  XCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import type { BadgeProps } from '@/components/ui/badge';
import type { SubAgentStatus } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';

interface StatusMeta {
  labelKey: string;
  icon: LucideIcon;
  variant: NonNullable<BadgeProps['variant']>;
  /** Fill colour for the progress bar in this state. */
  bar: string;
  spin?: boolean;
}

const SUBAGENT_STATUS_META: Record<SubAgentStatus, StatusMeta> = {
  idle: { labelKey: 'status.idle', icon: CircleDashed, variant: 'neutral', bar: 'bg-fg-muted' },
  running: {
    labelKey: 'status.running',
    icon: Loader2,
    variant: 'info',
    bar: 'bg-info-fg',
    spin: true,
  },
  paused: {
    labelKey: 'status.paused',
    icon: PauseCircle,
    variant: 'warning',
    bar: 'bg-warning-fg',
  },
  completed: {
    labelKey: 'status.completed',
    icon: CheckCircle2,
    variant: 'success',
    bar: 'bg-success-fg',
  },
  failed: { labelKey: 'status.failed', icon: XCircle, variant: 'danger', bar: 'bg-danger-fg' },
  cancelled: { labelKey: 'status.cancelled', icon: Ban, variant: 'neutral', bar: 'bg-fg-muted' },
  timeout: { labelKey: 'status.timeout', icon: TimerOff, variant: 'warning', bar: 'bg-warning-fg' },
};

/** Colour-coded lifecycle badge. */
export function SubagentStatusBadge({
  status,
  className,
}: {
  status: SubAgentStatus;
  className?: string;
}) {
  const { t } = useTranslation('subagents');
  const meta = SUBAGENT_STATUS_META[status];
  const Icon = meta.icon;
  return (
    <Badge variant={meta.variant} className={className}>
      <Icon
        className={cn('size-3', meta.spin && 'animate-spin motion-reduce:animate-none')}
        aria-hidden
      />
      {t(meta.labelKey)}
    </Badge>
  );
}

/** Determinate progress bar tinted by status. `value` is 0–1. */
export function ProgressBar({
  value,
  status,
  label,
  className,
}: {
  value: number;
  status: SubAgentStatus;
  label: string;
  className?: string;
}) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-sunken', className)}
    >
      <div
        className={cn(
          'h-full rounded-full transition-all duration-normal',
          SUBAGENT_STATUS_META[status].bar,
        )}
        style={{ inlineSize: `${percent}%` }}
      />
    </div>
  );
}
