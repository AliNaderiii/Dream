import { explainMemoryScore } from '@/components/memory/memory-score-model';
import type { BridgeMemory } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function MemoryScore({
  memory,
  compact = false,
}: {
  memory: BridgeMemory;
  compact?: boolean;
}) {
  const { t } = useTranslation('memory');
  const parts = explainMemoryScore(memory);
  const shownScore = clamp(memory.score);

  return (
    <div
      aria-label={t('score.label', { score: Math.round(shownScore * 100) })}
      className={cn('w-full', compact ? 'mt-1' : 'rounded-lg bg-sunken p-3')}
    >
      <div className="mb-2 flex items-center justify-between gap-2 text-micro">
        <span className="font-semibold text-fg-secondary">{t('score.title')}</span>
        <span className="tabular font-semibold text-accent-text">
          {memory.score > 0 ? `${Math.round(shownScore * 100)}%` : t('score.notRanked')}
        </span>
      </div>
      <div className={cn('grid gap-2', compact ? 'grid-cols-4' : 'grid-cols-2')}>
        {parts.map((part) => (
          <div key={part.factor}>
            <div className="mb-1 flex items-center justify-between gap-1 text-micro text-fg-muted">
              <span>{t(`score.factor.${part.factor}`)}</span>
              {!compact && <span className="tabular">{Math.round(part.weight * 100)}%</span>}
            </div>
            <div
              role="meter"
              aria-label={t('score.factorLabel', { factor: t(`score.factor.${part.factor}`) })}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round((part.value ?? 0) * 100)}
              aria-valuetext={
                part.value === null ? t('score.unavailable') : `${Math.round(part.value * 100)}%`
              }
              className="h-1.5 overflow-hidden rounded-full bg-surface-2"
            >
              <span
                className="block h-full rounded-full bg-accent"
                style={{ inlineSize: `${Math.round((part.value ?? 0) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      {!compact && (
        <div className="mt-3 flex flex-col gap-1 text-micro text-fg-muted">
          <p>{t('score.formula')}</p>
          {parts[0].value === null && <p>{t('score.relevanceUnavailable')}</p>}
        </div>
      )}
    </div>
  );
}
