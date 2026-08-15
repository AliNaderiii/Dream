/**
 * Standard empty state: 24px icon, one-line explanation, optional action.
 * Every screen ships one (design-system §8).
 */

import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import { Button } from '@/components/ui/button';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
  children?: ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action, children }: EmptyStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <Icon className="size-6 text-fg-muted" aria-hidden />
      <h2 className="text-h2 font-semibold">{title}</h2>
      <p className="max-w-md text-body text-fg-secondary">{description}</p>
      {action && (
        <Button variant="primary" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
      {children}
    </div>
  );
}
