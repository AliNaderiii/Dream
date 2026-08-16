/**
 * Importance rendered as ten stars.
 *
 * Dream stores importance as a 0.0–1.0 float; the UI trades in whole stars, and
 * the conversion lives in `lib/bridge/memory.ts`. This component only ever sees
 * the 0–10 integer.
 */

import { Star } from 'lucide-react';

import { MAX_STARS } from '@/lib/bridge/memory';
import { cn } from '@/utils/cn';

interface ImportanceStarsProps {
  /** Whole stars, 0–10. */
  value: number;
  /** Compact rendering for list rows: filled count instead of ten glyphs. */
  compact?: boolean;
  className?: string;
}

/** Read-only star display with a text alternative for screen readers. */
export function ImportanceStars({ value, compact = false, className }: ImportanceStarsProps) {
  const filled = Math.max(0, Math.min(MAX_STARS, Math.round(value)));
  const label = `Importance ${filled} out of ${MAX_STARS}`;

  if (compact) {
    return (
      <span
        className={cn('inline-flex items-center gap-1 text-caption text-fg-secondary', className)}
        title={label}
      >
        <Star className="size-3.5 fill-current text-chart-2" aria-hidden />
        <span className="tabular">{filled}</span>
        <span className="sr-only">{label}</span>
      </span>
    );
  }

  return (
    <span
      className={cn('inline-flex items-center gap-0.5', className)}
      role="img"
      aria-label={label}
    >
      {Array.from({ length: MAX_STARS }, (_, index) => (
        <Star
          key={index}
          aria-hidden
          className={cn(
            'size-3.5',
            index < filled ? 'fill-current text-chart-2' : 'text-border-strong',
          )}
        />
      ))}
    </span>
  );
}

interface ImportanceSliderProps {
  /** Whole stars, 0–10. */
  value: number;
  onChange: (value: number) => void;
  label: string;
  id?: string;
  disabled?: boolean;
}

/** Editable importance control — a native range input for full keyboard support. */
export function ImportanceSlider({ value, onChange, label, id, disabled }: ImportanceSliderProps) {
  return (
    <div className="flex items-center gap-3">
      <input
        id={id}
        type="range"
        min={0}
        max={MAX_STARS}
        step={1}
        value={value}
        disabled={disabled}
        aria-label={label}
        aria-valuetext={`${value} of ${MAX_STARS}`}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-1.5 w-40 cursor-pointer appearance-none rounded-full bg-sunken accent-[var(--accent-solid)] disabled:cursor-not-allowed disabled:opacity-50"
      />
      <span className="tabular w-8 shrink-0 text-caption text-fg-secondary">{value}</span>
    </div>
  );
}
