import type { ComponentProps } from 'react';

import { cn } from '@/utils/cn';

interface SwitchProps extends Omit<ComponentProps<'button'>, 'onChange'> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  description?: string;
}

/** RTL-native switch: logical flex direction mirrors while the knob uses inline translation. */
export function Switch({
  checked,
  onCheckedChange,
  label,
  description,
  className,
  disabled,
  ...props
}: SwitchProps) {
  return (
    <span className={cn('inline-flex items-center gap-3', className)}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          'relative h-5 w-9 shrink-0 rounded-full border border-border-strong transition-colors duration-fast disabled:opacity-50',
          checked ? 'bg-accent' : 'bg-sunken',
        )}
        {...props}
      >
        <span
          aria-hidden
          className={cn(
            'absolute start-0.5 top-0.5 size-3.5 rounded-full bg-surface-raised shadow-e1 transition-transform duration-fast ease-standard',
            checked && 'translate-x-4 rtl:-translate-x-4',
          )}
        />
      </button>
      <span className="flex flex-col text-start">
        <span className="text-body font-medium text-fg-primary">{label}</span>
        {description && <span className="text-caption text-fg-secondary">{description}</span>}
      </span>
    </span>
  );
}
