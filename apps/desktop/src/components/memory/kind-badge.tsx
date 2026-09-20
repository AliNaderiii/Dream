/**
 * Colour-coded memory-kind pill.
 *
 * The three kinds use the Okabe–Ito categorical ramp from `theme.css`
 * (semantic = chart-1 blue, episodic = chart-3 green, procedural = p-500
 * purple); the mapping lives in `kind-colors.ts`. Colour is never the only
 * signal: the kind name is always spelled out (design-system §2.3).
 */

import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';

import { KIND_COLOR } from '@/components/memory/kind-colors';

/** Title-cased label for a kind. */
function kindLabel(kind: string): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

interface KindBadgeProps {
  kind: string;
  className?: string;
}

export function KindBadge({ kind, className }: KindBadgeProps) {
  const { t } = useTranslation('memory');
  const color = KIND_COLOR[kind] ?? 'var(--color-chart-8)';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border-default bg-surface-2 px-2 py-0.5 text-micro font-semibold text-fg-secondary',
        className,
      )}
    >
      <span
        aria-hidden
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      {t(`kind.${kind}`, { defaultValue: kindLabel(kind) })}
    </span>
  );
}
