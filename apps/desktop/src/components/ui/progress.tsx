import type { ComponentProps } from 'react';
import { cn } from '@/utils/cn';

export interface ProgressProps extends ComponentProps<'div'> {
  value: number;
  max?: number;
  label?: string;
}

export function Progress({ value, max = 100, label, className, ...props }: ProgressProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={cn('w-full', className)} {...props}>
      {label && <div className="mb-1 text-caption font-medium text-fg-secondary">{label}</div>}
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label ?? 'Progress'}
        className="h-2 w-full overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-normal ease-standard"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
