import type { ComponentProps } from 'react';

import { cn } from '@/utils/cn';

export function Skeleton({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div aria-hidden className={cn('skeleton-shape min-h-3 rounded-md', className)} {...props} />
  );
}

/** Reusable loading geometry for card/list surfaces. */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-xl border border-border-default bg-surface p-4" aria-hidden>
      <div className="flex items-center gap-3">
        <Skeleton className="size-9 rounded-full" />
        <div className="flex flex-1 flex-col gap-2">
          <Skeleton className="h-3 w-2/5" />
          <Skeleton className="h-2.5 w-1/4" />
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-2">
        {Array.from({ length: lines }, (_, index) => (
          <Skeleton key={index} className={cn('h-3', index === lines - 1 ? 'w-3/5' : 'w-full')} />
        ))}
      </div>
    </div>
  );
}
