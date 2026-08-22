import type { BridgeMemory } from '@/lib/bridge/types';

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
