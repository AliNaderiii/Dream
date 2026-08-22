import { useTranslation } from '@/lib/i18n';
import type { BridgeMemory } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

const HALF_LIFE_SECONDS = 30 * 24 * 60 * 60;

export const MEMORY_SCORE_WEIGHTS = {
  relevance: 0.55,
  recency: 0.2,
  importance: 0.15,
  usage: 0.1,
} as const;

export type MemoryScoreFactor = keyof typeof MEMORY_SCORE_WEIGHTS;

export interface MemoryScorePart {
  factor: MemoryScoreFactor;
  value: number | null;
  weight: number;
  contribution: number | null;
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/** Mirrors the protocol-v3.16 retrieval formula without mutating memory data. */
export function explainMemoryScore(
  memory: BridgeMemory,
  nowSeconds = Date.now() / 1000,
): MemoryScorePart[] {
  const age = Math.max(0, nowSeconds - memory.created_at);
  const recency = Math.exp((-Math.log(2) * age) / HALF_LIFE_SECONDS);
  const importance = clamp(memory.importance);
  const usage = 1 - Math.exp(-Math.max(0, memory.use_count) / 5);
  const knownContribution =
    MEMORY_SCORE_WEIGHTS.recency * recency +
    MEMORY_SCORE_WEIGHTS.importance * importance +
    MEMORY_SCORE_WEIGHTS.usage * usage;
  const relevance =
    memory.score > 0
      ? clamp((memory.score - knownContribution) / MEMORY_SCORE_WEIGHTS.relevance)
      : null;
  const values: Record<MemoryScoreFactor, number | null> = {
    relevance,
    recency,
    importance,
    usage,
  };
  return (Object.keys(MEMORY_SCORE_WEIGHTS) as MemoryScoreFactor[]).map((factor) => {
    const value = values[factor];
    const weight = MEMORY_SCORE_WEIGHTS[factor];
    return { factor, value, weight, contribution: value === null ? null : value * weight };
  });
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
              aria-valuenow={part.value === null ? undefined : Math.round(part.value * 100)}
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
