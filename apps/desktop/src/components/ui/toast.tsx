import { AlertCircle, CheckCircle2, Info, TriangleAlert, X } from 'lucide-react';
import type { ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/utils/cn';

export type ToastTone = 'neutral' | 'success' | 'warning' | 'danger';

export interface ToastNotice {
  id: string;
  title: string;
  description?: string;
  tone?: ToastTone;
  action?: ReactNode;
}

interface ToastViewportProps {
  notices: ToastNotice[];
  onDismiss: (id: string) => void;
  label: string;
  dismissLabel: string;
  className?: string;
}

const TONE = {
  neutral: { icon: Info, className: 'text-info-fg' },
  success: { icon: CheckCircle2, className: 'text-success-fg' },
  warning: { icon: TriangleAlert, className: 'text-warning-fg' },
  danger: { icon: AlertCircle, className: 'text-danger-fg' },
} satisfies Record<ToastTone, { icon: typeof Info; className: string }>;

/** Logical-corner toast stack. Urgent errors use alert; all other notices are polite. */
export function ToastViewport({
  notices,
  onDismiss,
  label,
  dismissLabel,
  className,
}: ToastViewportProps) {
  return (
    <div
      aria-label={label}
      className={cn(
        'pointer-events-none fixed bottom-8 end-4 z-70 flex w-[min(24rem,calc(100%-2rem))] flex-col gap-2',
        className,
      )}
    >
      {notices.slice(0, 3).map((notice) => {
        const tone = notice.tone ?? 'neutral';
        const config = TONE[tone];
        const Icon = config.icon;
        return (
          <section
            key={notice.id}
            role={tone === 'danger' ? 'alert' : 'status'}
            className="motion-enter pointer-events-auto flex items-start gap-3 rounded-xl border border-border-default bg-overlay p-3 shadow-e2"
          >
            <Icon className={cn('mt-0.5 size-4 shrink-0', config.className)} aria-hidden />
            <div className="min-w-0 flex-1">
              <h3 className="text-body font-semibold">{notice.title}</h3>
              {notice.description && (
                <p className="mt-0.5 text-caption text-fg-secondary">{notice.description}</p>
              )}
              {notice.action && <div className="mt-2">{notice.action}</div>}
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={dismissLabel}
              onClick={() => onDismiss(notice.id)}
            >
              <X aria-hidden />
            </Button>
          </section>
        );
      })}
    </div>
  );
}
