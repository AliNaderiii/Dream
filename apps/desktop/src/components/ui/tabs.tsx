import { useId, useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';

import { cn } from '@/utils/cn';

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
  disabled?: boolean;
}

interface TabsProps {
  items: TabItem[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  variant?: 'underline' | 'pill';
  label: string;
  className?: string;
}

/** Keyboard-complete tabs with automatic activation and RTL visual arrows. */
export function Tabs({
  items,
  value,
  defaultValue,
  onValueChange,
  variant = 'underline',
  label,
  className,
}: TabsProps) {
  const prefix = useId();
  const enabled = items.filter((item) => !item.disabled);
  const fallback = defaultValue ?? enabled[0]?.id ?? '';
  const [internalValue, setInternalValue] = useState(fallback);
  const selected = value ?? internalValue;
  const refs = useRef(new Map<string, HTMLButtonElement>());

  const select = (id: string) => {
    if (value === undefined) setInternalValue(id);
    onValueChange?.(id);
  };

  const move = (event: KeyboardEvent, currentId: string) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || enabled.length === 0)
      return;
    event.preventDefault();
    const index = Math.max(
      0,
      enabled.findIndex((item) => item.id === currentId),
    );
    const rtl = document.documentElement.dir === 'rtl';
    const visualNext = event.key === 'ArrowRight' ? 1 : -1;
    const step = rtl ? -visualNext : visualNext;
    const nextIndex =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? enabled.length - 1
          : (index + step + enabled.length) % enabled.length;
    const next = enabled[nextIndex];
    if (next) {
      select(next.id);
      refs.current.get(next.id)?.focus();
    }
  };

  const active = items.find((item) => item.id === selected) ?? enabled[0];

  return (
    <div className={cn('min-w-0', className)}>
      <div
        role="tablist"
        aria-label={label}
        className={cn(
          'flex items-center gap-1',
          variant === 'underline'
            ? 'border-b border-border-default'
            : 'rounded-lg bg-surface-2 p-1',
        )}
      >
        {items.map((item) => {
          const activeItem = item.id === active?.id;
          return (
            <button
              key={item.id}
              ref={(node) => {
                if (node) refs.current.set(item.id, node);
                else refs.current.delete(item.id);
              }}
              type="button"
              role="tab"
              id={`${prefix}-${item.id}-tab`}
              aria-controls={`${prefix}-${item.id}-panel`}
              aria-selected={activeItem}
              tabIndex={activeItem ? 0 : -1}
              disabled={item.disabled}
              onClick={() => select(item.id)}
              onKeyDown={(event) => move(event, item.id)}
              className={cn(
                'relative control-sm text-caption font-medium text-fg-secondary transition-[background-color,color] duration-fast',
                'disabled:pointer-events-none disabled:opacity-50',
                variant === 'underline'
                  ? 'rounded-t-md after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:origin-center after:scale-x-0 after:rounded-full after:bg-accent after:transition-transform after:duration-normal'
                  : 'rounded-md',
                activeItem &&
                  (variant === 'underline'
                    ? 'text-accent-text after:scale-x-100'
                    : 'bg-surface text-fg-primary shadow-e1'),
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {active && (
        <div
          role="tabpanel"
          id={`${prefix}-${active.id}-panel`}
          aria-labelledby={`${prefix}-${active.id}-tab`}
          tabIndex={0}
          className="motion-enter py-3 outline-none"
        >
          {active.content}
        </div>
      )}
    </div>
  );
}
