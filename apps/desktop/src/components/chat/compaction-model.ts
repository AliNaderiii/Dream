/**
 * Pure models for the visible compaction bar (MEM Stage F).
 *
 * Laws pinned by the tests:
 * - tokens saved never go negative, and the reclaimed share is a whole
 *   percentage rounded from the true fraction;
 * - a payload that did not actually compact produces no row — the bar says
 *   so instead of inventing history;
 * - a partial payload fills defaults rather than rendering `undefined`;
 * - the nudge indicator hides when nudges are off, already sent, or when its
 *   state could not be read at all (unknown ≠ due).
 */

/** Wire shape of `conversation.compact`'s result. */
export interface CompactionWirePayload {
  compacted?: boolean;
  before_tokens?: number;
  after_tokens?: number;
  preserved_messages?: number;
  reason?: string;
  summary?: string;
}

/** One rendered compaction row. */
export interface CompactionRow {
  beforeTokens: number;
  afterTokens: number;
  savedTokens: number;
  reclaimedPercent: number;
  preservedMessages: number;
  reason: string;
  summary: string;
}

function finiteOr(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

/** Build a row, or `null` when the payload did not actually compact. */
export function toCompactionRow(payload: CompactionWirePayload): CompactionRow | null {
  if (!payload || payload.compacted !== true) return null;
  const beforeTokens = Math.max(0, finiteOr(payload.before_tokens, 0));
  const afterTokens = Math.max(0, finiteOr(payload.after_tokens, beforeTokens));
  // Saved is clamped at zero: a compact that grew the context freed nothing.
  const savedTokens = Math.max(0, beforeTokens - afterTokens);
  const reclaimedPercent = beforeTokens > 0 ? Math.round((100 * savedTokens) / beforeTokens) : 0;
  return {
    beforeTokens,
    afterTokens,
    savedTokens,
    reclaimedPercent,
    preservedMessages: Math.max(0, finiteOr(payload.preserved_messages, 0)),
    reason: typeof payload.reason === 'string' && payload.reason ? payload.reason : 'threshold',
    summary: typeof payload.summary === 'string' ? payload.summary : '',
  };
}

/** Wire shape of `nudge.status`; `null` means the state could not be read. */
export type NudgeWireStatus = { enabled: boolean; sent: boolean; due: boolean } | null;

/** The absolute off-switch: unknown, disabled, or already sent → hidden. */
export function nudgeVisible(status: NudgeWireStatus): boolean {
  return status !== null && status.enabled && !status.sent && status.due;
}
