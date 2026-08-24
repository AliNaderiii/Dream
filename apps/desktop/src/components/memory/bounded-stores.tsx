/**
 * Bounded stores panel (MEM Stage F): the two fixed-size stores whose entire
 * content rides with every system prompt.
 *
 * Laws pinned by the tests:
 *
 * - **Nothing is written without consent.** Every add/edit/remove opens the
 *   shared `ApprovalDialog` (fed a synthesised `PendingApproval`) and only
 *   `allow_once` / `allow_always_session` perform the bridge call; a denial
 *   or a dismissal re-reads the store and writes nothing.
 * - **A refused write changes nothing.** The kernel's bilingual refusal is
 *   rendered verbatim next to an untouched entry list.
 * - **The session prompt is frozen.** The panel states that the prompt was
 *   built from a snapshot frozen at session start, and only *adds* a note
 *   when today's store differs from that frozen pair.
 * - **The header is a prompt contract.** The kernel-rendered
 *   `[67% — 1,474/2,200 chars]` string is shown inside an LTR island,
 *   byte-for-byte under every locale.
 */

import { BookLock, PencilLine, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApprovalDialog } from '@/components/chat/approval-dialog';
import { EmptyState } from '@/components/shared/empty-state';
import { VirtualList } from '@/components/shared/virtual-list';
import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import {
  addBoundedMemory,
  boundedPercent,
  removeBoundedMemory,
  replaceBoundedMemory,
  type BoundedMemorySnapshot,
  type BoundedMemoryTarget,
} from '@/lib/bridge/memory';
import { useTranslation } from '@/lib/i18n';
import type { PendingApproval } from '@/types';
import { cn } from '@/utils/cn';

/** Reads may walk a slow store; writes are tiny but still bounded. */
const READ_TIMEOUT_MS = 15_000;
const WRITE_TIMEOUT_MS = 10_000;

const TARGETS: readonly BoundedMemoryTarget[] = ['memory', 'user'];

/** One consented, described write waiting for an approval decision. */
interface PendingWrite {
  kind: 'add' | 'replace' | 'remove';
  target: BoundedMemoryTarget;
  /** `old` fragment for replace/remove; full new text for add/replace. */
  old?: string;
  text?: string;
}

type Snapshots = Record<BoundedMemoryTarget, BoundedMemorySnapshot | null>;

let approvalSeq = 0;

export function BoundedStores() {
  const { t } = useTranslation('memory');
  const { client, state } = useBridge();
  const offline = state === 'disconnected';

  const [snapshots, setSnapshots] = useState<Snapshots>({ memory: null, user: null });
  const [frozenHeaders, setFrozenHeaders] = useState<Record<BoundedMemoryTarget, string> | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [pendingWrite, setPendingWrite] = useState<PendingWrite | null>(null);

  const loadGeneration = useRef(0);

  const readAll = useCallback(
    async (options?: { signal?: AbortSignal }) => {
      const live = await client.call<Record<BoundedMemoryTarget, BoundedMemorySnapshot>>(
        'memory2.snapshot',
        {},
        { timeoutMs: READ_TIMEOUT_MS, signal: options?.signal },
      );
      const frozen = await client.call<Record<BoundedMemoryTarget, BoundedMemorySnapshot>>(
        'memory2.status',
        {},
        { timeoutMs: READ_TIMEOUT_MS, signal: options?.signal },
      );
      return { live, frozen };
    },
    [client],
  );

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++loadGeneration.current;
    const load = async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const { live, frozen } = await readAll({ signal: controller.signal });
        if (controller.signal.aborted) return;
        setSnapshots({ memory: live.memory ?? null, user: live.user ?? null });
        setFrozenHeaders({ memory: frozen.memory.header, user: frozen.user.header });
      } catch (err) {
        if (controller.signal.aborted || generation !== loadGeneration.current) return;
        setLoadError(err instanceof Error ? err.message : t('bounded.failedLoad'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    // State updates stay out of the effect body (react-hooks lint).
    void Promise.resolve().then(() => void load());
    return () => controller.abort();
  }, [readAll, t]);

  const refresh = useCallback(async () => {
    const generation = ++loadGeneration.current;
    try {
      const { live } = await readAll();
      if (generation !== loadGeneration.current) return;
      setSnapshots({ memory: live.memory ?? null, user: live.user ?? null });
    } catch (err) {
      if (generation !== loadGeneration.current) return;
      setLoadError(err instanceof Error ? err.message : t('bounded.failedLoad'));
    }
  }, [readAll, t]);

  /** Apply the consented write; a refusal is rendered verbatim, nothing more. */
  const performWrite = useCallback(
    async (write: PendingWrite) => {
      setWriteError(null);
      try {
        if (write.kind === 'add') {
          const result = await addBoundedMemory(client, write.target, write.text ?? '', {
            timeoutMs: WRITE_TIMEOUT_MS,
          });
          setSnapshots((prev) => ({ ...prev, [write.target]: result }));
        } else if (write.kind === 'replace') {
          const result = await replaceBoundedMemory(
            client,
            write.target,
            write.old ?? '',
            write.text ?? '',
            { timeoutMs: WRITE_TIMEOUT_MS },
          );
          setSnapshots((prev) => ({ ...prev, [write.target]: result }));
        } else {
          const result = await removeBoundedMemory(client, write.target, write.old ?? '', {
            timeoutMs: WRITE_TIMEOUT_MS,
          });
          setSnapshots((prev) => ({ ...prev, [write.target]: result }));
        }
      } catch (err) {
        setWriteError(err instanceof Error ? err.message : t('bounded.writeFailed'));
        // A refused write changes nothing on the wire; re-read so the panel
        // proves it rather than assuming it.
        await refresh();
      }
    },
    [client, refresh, t],
  );

  const requestWrite = (write: PendingWrite) => {
    setWriteError(null);
    setPendingWrite(write);
  };

  const approval: PendingApproval | null = pendingWrite
    ? {
        approvalId: `bounded-${++approvalSeq}`,
        toolName:
          pendingWrite.target === 'memory'
            ? `agent_notes.${pendingWrite.kind}`
            : `user_profile.${pendingWrite.kind}`,
        argsSummary:
          pendingWrite.kind === 'remove'
            ? `${pendingWrite.old ?? ''}`
            : `${pendingWrite.old ? `${pendingWrite.old} → ` : ''}${pendingWrite.text ?? ''}`,
        risk: 'guarded',
        paneId: 'memory-bounded',
      }
    : null;

  return (
    <section aria-label={t('bounded.title')} className="flex h-full min-h-0 flex-col">
      <header className="border-b border-border-default px-4 pb-3 pt-4">
        <h2 className="text-h3 font-semibold text-fg-primary">{t('bounded.title')}</h2>
        <p className="mt-1 max-w-prose text-caption text-fg-muted">{t('bounded.description')}</p>
        <p className="mt-2 flex items-center gap-2 text-caption text-fg-secondary">
          <BookLock aria-hidden className="size-4 shrink-0 text-accent-text" />
          <span>
            <span className="font-medium">{t('bounded.frozenTitle')}</span>{' '}
            {t('bounded.frozenDesc')}
          </span>
        </p>
      </header>

      {writeError && (
        <p
          role="alert"
          className="border-b border-danger-fg bg-danger-bg px-4 py-2 text-caption text-danger-fg bidi-isolate"
          dir="auto"
        >
          {writeError}
        </p>
      )}

      {loadError && (
        <div
          role="alert"
          className="flex items-center gap-3 border-b border-danger-fg bg-danger-bg px-4 py-2 text-caption text-danger-fg"
        >
          <span className="min-w-0 flex-1">{loadError}</span>
          <Button size="sm" variant="secondary" onClick={() => void refresh()}>
            {t('bounded.retry')}
          </Button>
        </div>
      )}

      {loading ? (
        <div role="status" aria-label={t('bounded.loading')} className="flex flex-col gap-2 p-4">
          {Array.from({ length: 4 }, (_, index) => (
            <div
              key={index}
              className="h-24 animate-pulse rounded-xl bg-surface-2 motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 lg:grid-cols-2">
          {TARGETS.map((target) => (
            <StoreSection
              key={target}
              target={target}
              snapshot={snapshots[target]}
              frozenHeader={frozenHeaders?.[target] ?? null}
              offline={offline}
              onRequestWrite={requestWrite}
            />
          ))}
        </div>
      )}

      {approval && (
        <ApprovalDialog
          approval={approval}
          onDecision={(decision) => {
            const write = pendingWrite;
            setPendingWrite(null);
            // Fail-closed: dismissal and refusal write nothing.
            if (!write || decision === 'deny') {
              void refresh();
              return;
            }
            void performWrite(write);
          }}
        />
      )}
    </section>
  );
}

interface StoreSectionProps {
  target: BoundedMemoryTarget;
  snapshot: BoundedMemorySnapshot | null;
  frozenHeader: string | null;
  offline: boolean;
  onRequestWrite: (write: PendingWrite) => void;
}

function StoreSection({
  target,
  snapshot,
  frozenHeader,
  offline,
  onRequestWrite,
}: StoreSectionProps) {
  const { t } = useTranslation('memory');
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState<{ old: string; text: string } | null>(null);

  const entries = snapshot?.entries ?? [];
  const percent = snapshot ? boundedPercent(snapshot.used_chars, snapshot.capacity) : 0;
  const drifted = Boolean(snapshot && frozenHeader && snapshot.header !== frozenHeader);

  const submitAdd = () => {
    const text = draft.trim();
    if (!text) return;
    onRequestWrite({ kind: 'add', target, text });
    setDraft('');
  };

  const submitEdit = () => {
    if (!editing) return;
    const text = editing.text.trim();
    if (!text || text === editing.old) {
      setEditing(null);
      return;
    }
    onRequestWrite({ kind: 'replace', target, old: editing.old, text });
    setEditing(null);
  };

  return (
    <section
      aria-label={t(`bounded.target.${target}`)}
      className="flex min-h-0 flex-col rounded-xl border border-border-default bg-surface p-3"
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-caption font-semibold uppercase tracking-wide text-fg-muted">
          {t(`bounded.target.${target}`)}
        </h3>
        <span className="text-micro text-fg-muted">
          {t('bounded.entryCount', { rows: entries.length })}
        </span>
      </div>

      {snapshot && (
        <div className="mt-2">
          <div
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t('bounded.meter', { target: t(`bounded.target.${target}`) })}
            className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
          >
            <div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
          </div>
          <p className="mt-1 text-micro text-fg-muted">
            {/* Prompt contract: kernel-rendered, LTR under every locale. */}
            <span dir="ltr" className="ltr-island font-medium text-fg-secondary">
              {snapshot.header}
            </span>
          </p>
          {drifted && (
            <p className="mt-1 text-micro text-accent-text">{t('bounded.frozenChanged')}</p>
          )}
        </div>
      )}

      {entries.length === 0 ? (
        <EmptyState
          icon={BookLock}
          title={t('bounded.empty')}
          description={t('bounded.emptyDesc')}
        />
      ) : (
        <VirtualList
          items={entries}
          getKey={(entry, index) => `${index}-${entry}`}
          estimateSize={editing ? 120 : 52}
          virtualizeAt={0}
          ariaLabel={t('bounded.entriesLabel')}
          className="mt-2 min-h-24 flex-1"
          renderItem={(entry, index) =>
            editing?.old === entry ? (
              <div className="flex h-full flex-col justify-center gap-2 py-1">
                <textarea
                  value={editing.text}
                  onChange={(event) => setEditing({ ...editing, text: event.target.value })}
                  aria-label={t('bounded.editLabel')}
                  rows={2}
                  dir="auto"
                  className="w-full rounded-lg border border-border-default bg-surface px-2 py-1.5 text-caption text-fg-primary"
                />
                <div className="flex gap-2">
                  <Button size="sm" variant="primary" disabled={offline} onClick={submitEdit}>
                    {t('bounded.save')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                    {t('bounded.cancel')}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center gap-2 py-1">
                <p
                  className="min-w-0 flex-1 truncate text-caption text-fg-primary bidi-isolate"
                  dir="auto"
                  title={entry}
                >
                  {entry}
                </p>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={offline}
                  aria-label={t('bounded.editAria', { index: index + 1 })}
                  onClick={() => setEditing({ old: entry, text: entry })}
                >
                  <PencilLine aria-hidden className="size-4" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={offline}
                  aria-label={t('bounded.removeAria', { index: index + 1 })}
                  onClick={() => onRequestWrite({ kind: 'remove', target, old: entry })}
                >
                  <Trash2 aria-hidden className="size-4 text-danger-fg" />
                </Button>
              </div>
            )
          }
        />
      )}

      <div className="mt-3 flex flex-col gap-2 border-t border-border-default pt-3">
        <label className="sr-only" htmlFor={`bounded-add-${target}`}>
          {t('bounded.addLabel')}
        </label>
        <textarea
          id={`bounded-add-${target}`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t('bounded.addPlaceholder')}
          rows={2}
          dir="auto"
          className={cn(
            'w-full rounded-lg border border-border-default bg-surface px-2 py-1.5 text-caption text-fg-primary',
            offline && 'opacity-60',
          )}
        />
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={offline || !draft.trim()}
            onClick={submitAdd}
          >
            <Plus aria-hidden className="size-4" />
            {t('bounded.add')}
          </Button>
        </div>
      </div>
    </section>
  );
}
