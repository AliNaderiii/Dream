import type { ComponentProps, ReactNode } from 'react';
import { cn } from '@/utils/cn';

export interface EmptyStateProps extends ComponentProps<'section'> {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action, className, ...props }: EmptyStateProps) {
  return (
    <section
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-xl border border-border-default bg-surface-raised px-8 py-12 text-center shadow-e1',
        className,
      )}
      aria-label={title}
      {...props}
    >
      <h3 className="text-h3 font-semibold text-fg-primary">{title}</h3>
      {description && <p className="text-caption text-fg-secondary">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </section>
  );
}
