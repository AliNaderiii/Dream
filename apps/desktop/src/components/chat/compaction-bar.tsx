/**
 * Compaction bar (MEM Stage F): the visible transcript compaction strip.
 *
 * Laws pinned by the tests:
 * - every compaction leaves a row with the before/after cost, the reclaimed
 *   share, what was preserved verbatim and what the summary kept; a payload
 *   that did not compact produces *no* row, just a notice;
 * - a refusal is rendered without losing the affordance;
 * - the nudge indicator is hidden when nudges are off, already sent, or when
 *   its state could not be read (no error banner for an unreadable nudge);
 * - compression disables while the bridge is offline, and the nudge read is
 *   cancelled on unmount.
 */

import { Archive, BellRing } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  toCompactionRow,
  nudgeVisible,
  type CompactionRow,
  type NudgeWireStatus,
} from '@/components/chat/compaction-model';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';

const READ_TIMEOUT_MS = 15_000;
const COMPACT_TIMEOUT_MS = 20_000;

export interface CompactionBarProps {
  sessionId: string | null;
}

export function CompactionBar({ sessionId }: CompactionBarProps) {
  const { t } = useTranslation('chat');
  const { client, state } = useBridge();
  const offline = state === 'disconnected';

  const [rows, setRows] = useState<CompactionRow[]>([]);
  const [nudge, setNudge] = useState<NudgeWireStatus>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [compressing, setCompressing] = useState(false);

  // Rows are session-scoped: observed events only, never replayed history.
  useEffect(() => {
    const reset = () => {
      setRows([]);
      setNotice(null);
      setError(null);
    };
    // Deferred: no setState runs synchronously in the effect body.
    void Promise.resolve().then(reset);
  }, [sessionId]);

  // The nudge read is cancellable; an unreadable state stays null (hidden).
  useEffect(() => {
    if (!sessionId) {
      const clear = () => setNudge(null);
      void Promise.resolve().then(clear);
      return;
    }
    const controller = new AbortController();
    const load = async () => {
      try {
        const out = await client.call<{ enabled: boolean; sent: boolean; due: boolean }>(
          'nudge.status',
          { session_id: sessionId },
          { timeoutMs: READ_TIMEOUT_MS, signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          setNudge(out && typeof out.enabled === 'boolean' ? out : null);
        }
      } catch {
        if (!controller.signal.aborted) setNudge(null);
      }
    };
    void Promise.resolve().then(() => void load());
    return () => controller.abort();
  }, [client, sessionId]);

  const compress = useCallback(async () => {
    if (!sessionId || compressing) return;
    setCompressing(true);
    setNotice(null);
    setError(null);
    try {
      const out = await client.call<Parameters<typeof toCompactionRow>[0]>(
        'conversation.compact',
        { session_id: sessionId },
        { timeoutMs: COMPACT_TIMEOUT_MS },
      );
      const row = toCompactionRow(out ?? {});
      if (row) {
        setRows((prev) => [...prev, row]);
      } else {
        setNotice(t('compaction.nothingToCompact'));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('compaction.failed'));
    } finally {
      setCompressing(false);
    }
  }, [client, compressing, sessionId, t]);

  const showNudge = nudgeVisible(nudge);

  return (
    <section
      aria-label={t('compaction.title')}
      className="flex flex-col gap-1 border-b border-border-default bg-surface-2 px-3 py-1.5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={offline || !sessionId || compressing}
          onClick={() => void compress()}
        >
          <Archive aria-hidden className="size-4" />
          {compressing ? t('compaction.compressing') : t('compaction.compress')}
        </Button>
        <button
          type="button"
          disabled={offline || !sessionId || compressing}
          onClick={() => void compress()}
          className="ltr-island rounded-sm bg-sunken px-1.5 py-0.5 font-mono text-micro text-fg-secondary disabled:opacity-60"
        >
          /compress
        </button>
        {showNudge && (
          <p
            role="status"
            className="flex items-center gap-1 rounded-full bg-warning-bg px-2 py-0.5 text-micro text-warning-fg"
          >
            <BellRing aria-hidden className="size-3" />
            {t('compaction.nudgeDue')}
          </p>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-md bg-danger-bg px-2 py-1 text-caption text-danger-fg bidi-isolate"
          dir="auto"
        >
          {error}
        </p>
      )}
      {notice && !error && (
        <p role="status" className="px-1 text-micro text-fg-muted">
          {notice}
        </p>
      )}

      {rows.length > 0 && (
        <ul aria-label={t('compaction.rowsLabel')} className="flex flex-col gap-1">
          {rows.map((row, index) => (
            <li
              key={index}
              className="rounded-md border border-border-default bg-surface px-2 py-1 text-caption"
            >
              <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-fg-primary">
                <span className="ltr-island font-medium">
                  {t('compaction.row', {
                    before: row.beforeTokens,
                    after: row.afterTokens,
                    percent: row.reclaimedPercent,
                  })}
                </span>
                <span className="text-fg-muted">
                  {t('compaction.preserved', { messages: row.preservedMessages })}
                </span>
                <span className="text-fg-muted">
                  {t('compaction.saved', { tokens: row.savedTokens })}
                </span>
                <span className="text-micro text-fg-muted">
                  {row.reason === 'explicit'
                    ? t('compaction.reason.explicit')
                    : t('compaction.reason.threshold')}
                </span>
              </p>
              {row.summary && (
                <p
                  className={cn('mt-0.5 line-clamp-2 text-micro text-fg-muted bidi-isolate')}
                  dir="auto"
                >
                  {row.summary}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
