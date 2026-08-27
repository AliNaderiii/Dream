import { cn } from '@/utils/cn';

const HUES: Record<string, string> = {
  teal: 'fill-accent-fg',
  amber: 'fill-warning-fg',
  rose: 'fill-danger-fg',
  slate: 'fill-fg-muted',
  violet: 'fill-accent-text',
};

export function BotAvatar({
  shape = 'hex',
  hue = 'teal',
  className,
}: {
  shape?: string;
  hue?: string;
  className?: string;
}) {
  const fill = HUES[hue] ?? HUES.teal;
  return (
    <svg viewBox="0 0 24 24" className={cn('size-6', fill, className)} aria-hidden>
      {shape === 'circle' && <circle cx="12" cy="12" r="8" />}
      {shape === 'square' && <rect x="5" y="5" width="14" height="14" rx="2" />}
      {shape === 'diamond' && <polygon points="12,3 21,12 12,21 3,12" />}
      {shape === 'triangle' && <polygon points="12,4 21,20 3,20" />}
      {shape !== 'circle' && shape !== 'square' && shape !== 'diamond' && shape !== 'triangle' && (
        <polygon points="12,3 20,8 20,16 12,21 4,16 4,8" />
      )}
    </svg>
  );
}
