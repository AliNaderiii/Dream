/**
 * Skills learning workspace (MEM Stage F): use statistics, the proposal
 * inbox, the `/learn` dialog, and a version diff with reference listings.
 *
 * Laws pinned by the tests:
 *
 * - a proposal is written **only** on an explicit approve — the approve
 *   click is the consent, and a discard writes nothing;
 * - `/learn` resolves a source to a skill name *before* anything is
 *   committed, refuses a URL while network tools are off (the kernel's
 *   bilingual refusal is rendered verbatim), and never invents a source
 *   for an empty conversation;
 * - the version diff never crashes on a one-version or empty ledger
 *   (indices are clamped on read, never `length - 1` in state);
 * - while the bridge is offline the inbox and `/learn` controls disable.
 */

import { GitCompare, GraduationCap, Inbox, Lightbulb } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApprovalDialog } from '@/components/chat/approval-dialog';
import { EmptyState } from '@/components/shared/empty-state';
import { VirtualList } from '@/components/shared/virtual-list';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';
import {
  diffCounts,
  diffLines,
  summariseUses,
  type SkillStat,
  type SkillUseRow,
} from '@/components/skills/skills-v2-model';
import type { PendingApproval } from '@/types';
import { cn } from '@/utils/cn';

const READ_TIMEOUT_MS = 15_000;
const WRITE_TIMEOUT_MS = 10_000;

/** Wire shapes for the v2 families this panel consumes. */
interface SkillVersionRow {
  name: string;
  version: number;
  content: string;
  kind: string;
  created_at: number;
}

interface SkillProposalRow {
  proposal_id: string;
  name: string;
  description: string;
  body: string;
  action: string;
  created_at: number;
}

interface ReferenceRow {
  name: string;
  bytes: number;
}

interface LearnSourceResult {
  kind: 'path' | 'corpus' | 'conversation' | 'notes' | 'url';
  topic: string;
  text: string;
  existing: string | null;
}

/** One consented write waiting for an approval decision. */
interface PendingLearnSave {
  name: string;
  content: string;
}

let approvalSeq = 0;

export function SkillsV2() {
  const { t } = useTranslation('skills');
  const { t: tc } = useTranslation('common');
  const { client, state } = useBridge();
  const offline = state === 'disconnected';

  const [uses, setUses] = useState<SkillUseRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [networkEnabled, setNetworkEnabled] = useState<boolean | null>(null);

  const [inbox, setInbox] = useState<SkillProposalRow[]>([]);
  const [inboxNote, setInboxNote] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);

  const [learnOpen, setLearnOpen] = useState(false);
  const [learnDraft, setLearnDraft] = useState('');
  const [checking, setChecking] = useState(false);
  const [learnError, setLearnError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<LearnSourceResult | null>(null);
  const [pendingSave, setPendingSave] = useState<PendingLearnSave | null>(null);

  const [selected, setSelected] = useState<string | null>(null);

  const loadGeneration = useRef(0);

  const refresh = useCallback(
    async (options?: { signal?: AbortSignal }) => {
      const generation = ++loadGeneration.current;
      const [usesResult, statusResult, proposalsResult] = await Promise.all([
        client.call<{ uses: SkillUseRow[] }>(
          'skills.use_log',
          {},
          { timeoutMs: READ_TIMEOUT_MS, signal: options?.signal },
        ),
        client.call<{ network_enabled: boolean }>(
          'skills.learn_status',
          {},
          { timeoutMs: READ_TIMEOUT_MS, signal: options?.signal },
        ),
        client.call<{ proposals: SkillProposalRow[] }>(
          'skills.proposals',
          {},
          { timeoutMs: READ_TIMEOUT_MS, signal: options?.signal },
        ),
      ]);
      if (generation !== loadGeneration.current) return;
      setUses(usesResult.uses);
      setNetworkEnabled(statusResult.network_enabled);
      setInbox(proposalsResult.proposals);
    },
    [client],
  );

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setLoadError(null);
      try {
        await refresh({ signal: controller.signal });
      } catch (err) {
        if (controller.signal.aborted) return;
        setLoadError(err instanceof Error ? err.message : t('v2.failedLoad'));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void Promise.resolve().then(() => void load());
    return () => controller.abort();
  }, [refresh, t]);

  const stats = useMemo(() => summariseUses(uses), [uses]);

  const checkSource = async () => {
    const argument = learnDraft.trim();
    if (!argument) return;
    setChecking(true);
    setLearnError(null);
    setResolved(null);
    try {
      const out = await client.call<{ source: LearnSourceResult }>(
        'skills.learn_classify',
        { argument },
        { timeoutMs: READ_TIMEOUT_MS },
      );
      setResolved(out.source);
    } catch (err) {
      setLearnError(err instanceof Error ? err.message : t('learn.failed'));
    } finally {
      setChecking(false);
    }
  };

  const approveProposal = async (proposal: SkillProposalRow) => {
    setWriteError(null);
    setInboxNote(null);
    try {
      const out = await client.call<{ status: string }>(
        'skills.apply_proposal',
        { proposal_id: proposal.proposal_id },
        { timeoutMs: WRITE_TIMEOUT_MS },
      );
      setInboxNote(t('inbox.approved', { name: proposal.name, status: out.status }));
      const fresh = await client.call<{ proposals: SkillProposalRow[] }>(
        'skills.proposals',
        {},
        { timeoutMs: READ_TIMEOUT_MS },
      );
      setInbox(fresh.proposals);
    } catch (err) {
      setWriteError(err instanceof Error ? err.message : t('v2.failedLoad'));
    }
  };

  const discardProposal = async (proposal: SkillProposalRow) => {
    setWriteError(null);
    setInboxNote(null);
    try {
      await client.call(
        'skills.discard_proposal',
        { proposal_id: proposal.proposal_id },
        { timeoutMs: WRITE_TIMEOUT_MS },
      );
      setInboxNote(t('inbox.discarded', { name: proposal.name }));
      const fresh = await client.call<{ proposals: SkillProposalRow[] }>(
        'skills.proposals',
        {},
        { timeoutMs: READ_TIMEOUT_MS },
      );
      setInbox(fresh.proposals);
    } catch (err) {
      setWriteError(err instanceof Error ? err.message : t('v2.failedLoad'));
    }
  };

  const commitLearnSave = async (save: PendingLearnSave) => {
    setWriteError(null);
    try {
      await client.call(
        'skills.save',
        { name: save.name, content: save.content },
        { timeoutMs: WRITE_TIMEOUT_MS },
      );
      setLearnOpen(false);
      setLearnDraft('');
      setResolved(null);
      setSelected(save.name);
    } catch (err) {
      setLearnError(err instanceof Error ? err.message : t('learn.failed'));
    }
  };

  const approval: PendingApproval | null = pendingSave
    ? {
        approvalId: `learn-${++approvalSeq}`,
        toolName: `skills.save ${pendingSave.name}`,
        argsSummary: pendingSave.content.slice(0, 400),
        risk: 'guarded',
        paneId: 'skills-learn',
      }
    : null;

  return (
    <section aria-label={t('v2.tab')} className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border-default px-4 pb-3 pt-4">
        <div>
          <h2 className="text-h3 font-semibold text-fg-primary">{t('v2.tab')}</h2>
          <p className="mt-1 max-w-prose text-caption text-fg-muted">{t('learn.description')}</p>
        </div>
        <Button
          variant="secondary"
          disabled={offline}
          onClick={() => {
            setLearnError(null);
            setResolved(null);
            setLearnOpen(true);
          }}
        >
          <GraduationCap aria-hidden className="size-4" />
          {t('learn.open')}
        </Button>
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
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              const load = async () => {
                setLoadError(null);
                try {
                  await refresh();
                } catch (err) {
                  setLoadError(err instanceof Error ? err.message : t('v2.failedLoad'));
                } finally {
                  setLoading(false);
                }
              };
              void load();
            }}
          >
            {t('retry')}
          </Button>
        </div>
      )}

      {loading ? (
        <div role="status" aria-label={t('v2.loading')} className="flex flex-col gap-2 p-4">
          {Array.from({ length: 4 }, (_, index) => (
            <div
              key={index}
              className="h-16 animate-pulse rounded-xl bg-surface-2 motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 xl:grid-cols-2">
          <UseStats
            stats={stats}
            selected={selected}
            onSelect={(name) => setSelected(selected === name ? null : name)}
          />
          <ProposalInbox
            inbox={inbox}
            note={inboxNote}
            offline={offline}
            onApprove={(proposal) => void approveProposal(proposal)}
            onDiscard={(proposal) => void discardProposal(proposal)}
          />
          <SkillDetail name={selected} />
        </div>
      )}

      {learnOpen && (
        <Dialog open onOpenChange={(open) => !open && setLearnOpen(false)}>
          <DialogContent aria-label={t('learn.title')} className="max-w-xl">
            <DialogHeader>
              <DialogTitle>{t('learn.title')}</DialogTitle>
              <DialogDescription>{t('learn.kinds')}</DialogDescription>
            </DialogHeader>
            <DialogBody>
              {networkEnabled === false && (
                <p
                  role="status"
                  className="mb-3 rounded-lg bg-warning-bg px-3 py-2 text-caption text-warning-fg"
                >
                  {t('learn.networkOff')}
                </p>
              )}
              <label className="mb-1 block text-caption text-fg-secondary" htmlFor="learn-source">
                {t('learn.sourceLabel')}
              </label>
              <textarea
                id="learn-source"
                value={learnDraft}
                onChange={(event) => setLearnDraft(event.target.value)}
                placeholder={t('learn.placeholder')}
                rows={4}
                dir="auto"
                className="w-full rounded-lg border border-border-default bg-surface px-2 py-1.5 text-caption text-fg-primary"
              />
              <div className="mt-2 flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={checking || offline || !learnDraft.trim()}
                  onClick={() => void checkSource()}
                >
                  <Lightbulb aria-hidden className="size-4" />
                  {checking ? t('learn.checking') : t('learn.check')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setLearnOpen(false)}>
                  {t('learn.cancel')}
                </Button>
              </div>
              {learnError && (
                <p
                  role="alert"
                  dir="auto"
                  className="mt-3 rounded-lg bg-danger-bg px-3 py-2 text-caption text-danger-fg bidi-isolate"
                >
                  {learnError}
                </p>
              )}
              {resolved && (
                <div className="mt-3 rounded-lg border border-border-default bg-surface-2 p-3 text-caption">
                  <p className="font-medium text-fg-primary">
                    {t('learn.resolved', { name: resolved.topic })}{' '}
                    <span className="text-fg-muted">{t(`learn.kind.${resolved.kind}`)}</span>
                  </p>
                  <p className="mt-1 text-micro text-fg-muted">
                    {t('learn.chars', { count: resolved.text.length })}
                    {resolved.existing
                      ? ` · ${t('learn.merges', { name: resolved.existing })}`
                      : ''}
                  </p>
                  {resolved.kind === 'url' && networkEnabled === false && (
                    <p className="mt-2 text-micro text-warning-fg">{t('learn.offlineWarning')}</p>
                  )}
                </div>
              )}
            </DialogBody>
            <DialogFooter>
              <Button
                variant="primary"
                disabled={!resolved}
                onClick={() =>
                  resolved &&
                  setPendingSave({
                    name: resolved.topic,
                    content: `## Purpose\n\n${resolved.topic}\n\n## Instructions\n\n${resolved.text}`,
                  })
                }
              >
                {tc('generic.save')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {approval && (
        <ApprovalDialog
          approval={approval}
          onDecision={(decision) => {
            const save = pendingSave;
            setPendingSave(null);
            if (!save || decision === 'deny') return;
            void commitLearnSave(save);
          }}
        />
      )}
    </section>
  );
}

/** Per-skill run/failure statistics, virtualised for large ledgers. */
function UseStats({
  stats,
  selected,
  onSelect,
}: {
  stats: readonly SkillStat[];
  selected: string | null;
  onSelect: (name: string) => void;
}) {
  const { t } = useTranslation('skills');
  return (
    <section
      aria-label={t('stats.title')}
      className="flex min-h-0 flex-col rounded-xl border border-border-default bg-surface p-3"
    >
      <h3 className="text-caption font-semibold uppercase tracking-wide text-fg-muted">
        {t('stats.title')}
      </h3>
      {stats.length === 0 ? (
        <EmptyState icon={Inbox} title={t('stats.empty')} description={t('stats.emptyDesc')} />
      ) : (
        <VirtualList
          items={[...stats]}
          getKey={(stat) => stat.name}
          estimateSize={44}
          virtualizeAt={0}
          ariaLabel={t('stats.title')}
          className="mt-2 min-h-24 flex-1"
          renderItem={(stat) => (
            <div className="flex h-full items-center gap-2 py-1">
              <button
                type="button"
                onClick={() => onSelect(stat.name)}
                aria-current={selected === stat.name ? 'true' : undefined}
                className={cn(
                  'min-w-0 flex-1 truncate rounded-md px-2 py-1 text-start text-caption transition-colors duration-fast motion-reduce:transition-none',
                  selected === stat.name
                    ? 'bg-accent-soft font-medium text-accent-text'
                    : 'text-fg-primary hover:bg-surface-2',
                )}
              >
                {stat.name}
              </button>
              <span className="shrink-0 text-micro text-fg-muted">
                {stat.runs} {t('stats.runs')}
              </span>
              <span className="shrink-0 text-micro text-danger-fg">
                {stat.failures} {t('stats.failures')}
              </span>
              <span className="shrink-0 text-micro text-fg-muted">
                {t('stats.median')} {stat.medianMs} ms
              </span>
            </div>
          )}
        />
      )}
    </section>
  );
}

/** The pending-review queue: nothing is written without an explicit click. */
function ProposalInbox({
  inbox,
  note,
  offline,
  onApprove,
  onDiscard,
}: {
  inbox: readonly SkillProposalRow[];
  note: string | null;
  offline: boolean;
  onApprove: (proposal: SkillProposalRow) => void;
  onDiscard: (proposal: SkillProposalRow) => void;
}) {
  const { t } = useTranslation('skills');
  return (
    <section
      aria-label={t('inbox.title')}
      className="flex min-h-0 flex-col rounded-xl border border-border-default bg-surface p-3"
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-caption font-semibold uppercase tracking-wide text-fg-muted">
          {t('inbox.title')}
        </h3>
        <span className="text-micro text-fg-muted">{t('inbox.count', { rows: inbox.length })}</span>
      </div>
      {note && (
        <p
          role="status"
          className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-micro text-fg-secondary bidi-isolate"
          dir="auto"
        >
          {note}
        </p>
      )}
      {inbox.length === 0 ? (
        <p className="mt-2 px-1 py-6 text-center text-caption text-fg-muted">{t('inbox.empty')}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2 overflow-y-auto">
          {inbox.map((proposal) => (
            <li
              key={proposal.proposal_id}
              className="rounded-lg border border-border-default bg-surface-2 p-2"
            >
              <p className="text-caption font-medium text-fg-primary bidi-isolate" dir="auto">
                {proposal.name} · {proposal.action}
              </p>
              <p className="mt-0.5 text-micro text-fg-muted bidi-isolate" dir="auto">
                {proposal.description}
              </p>
              <div className="mt-2 flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offline}
                  aria-label={t('inbox.approveAria', { name: proposal.name })}
                  onClick={() => onApprove(proposal)}
                >
                  {t('inbox.approveAria', { name: proposal.name })}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={offline}
                  aria-label={t('inbox.discardAria', { name: proposal.name })}
                  onClick={() => onDiscard(proposal)}
                >
                  {t('inbox.discardAria', { name: proposal.name })}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Version diff + references for one selected skill. */
function SkillDetail({ name }: { name: string | null }) {
  const { t } = useTranslation('skills');
  const { client } = useBridge();
  const [versions, setVersions] = useState<SkillVersionRow[]>([]);
  const [references, setReferences] = useState<ReferenceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // DiffReview trap: an index state of `versions.length - 1` is -1 on an
  // empty ledger; null + clamp-on-read instead.
  const [fromVersion, setFromVersion] = useState<number | null>(null);
  const [toVersion, setToVersion] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      if (!name) {
        setVersions([]);
        setReferences(null);
        setError(null);
        return;
      }
      setError(null);
      try {
        const [versionResult, referenceResult] = await Promise.all([
          client.call<{ versions: SkillVersionRow[] }>(
            'skills.versions',
            { name },
            { timeoutMs: READ_TIMEOUT_MS, signal: controller.signal },
          ),
          client.call<{ references: ReferenceRow[] }>(
            'skills.references',
            { name },
            { timeoutMs: READ_TIMEOUT_MS, signal: controller.signal },
          ),
        ]);
        if (controller.signal.aborted) return;
        setVersions(versionResult.versions);
        setReferences(referenceResult.references);
        setFromVersion(null);
        setToVersion(null);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : t('v2.failedLoad'));
        }
      }
    };
    void load();
    return () => controller.abort();
  }, [client, name, t]);

  const from = useMemo(() => {
    if (versions.length < 2) return versions[0] ?? null;
    const index = fromVersion ?? versions.length - 2;
    return versions[Math.max(0, Math.min(index, versions.length - 1))] ?? null;
  }, [versions, fromVersion]);

  const to = useMemo(() => {
    if (versions.length === 0) return null;
    const index = toVersion ?? versions.length - 1;
    return versions[Math.max(0, Math.min(index, versions.length - 1))] ?? null;
  }, [versions, toVersion]);

  const lines = useMemo(() => (from && to ? diffLines(from.content, to.content) : []), [from, to]);
  const counts = useMemo(() => diffCounts(lines), [lines]);

  return (
    <section
      aria-label={t('v2.detailTitle')}
      className="flex min-h-0 flex-col rounded-xl border border-border-default bg-surface p-3 xl:col-span-2"
    >
      <h3 className="text-caption font-semibold uppercase tracking-wide text-fg-muted">
        {t('v2.detailTitle')}
        {name ? ` — ${name}` : ''}
      </h3>
      {error && (
        <p
          role="alert"
          className="mt-2 rounded-lg bg-danger-bg px-3 py-2 text-caption text-danger-fg"
        >
          {error}
        </p>
      )}
      {!name ? (
        <p className="px-1 py-6 text-center text-caption text-fg-muted">{t('selectSkill')}</p>
      ) : versions.length < 2 ? (
        <p role="status" className="mt-2 px-1 py-4 text-center text-caption text-fg-muted">
          {t('diff.needTwo')}
        </p>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-micro text-fg-muted">
            <GitCompare aria-hidden className="size-4" />
            <span>{t('diff.compare')}</span>
            <select
              aria-label={t('diff.versionPair')}
              value={from?.version}
              onChange={(event) => setFromVersion(Number(event.target.value))}
              className="rounded-md border border-border-default bg-surface px-1 py-0.5 text-micro"
            >
              {versions.map((row) => (
                <option key={row.version} value={row.version}>
                  {t('diff.label', { version: row.version })}
                </option>
              ))}
            </select>
            <select
              aria-label={t('diff.versionPair')}
              value={to?.version}
              onChange={(event) => setToVersion(Number(event.target.value))}
              className="rounded-md border border-border-default bg-surface px-1 py-0.5 text-micro"
            >
              {versions.map((row) => (
                <option key={row.version} value={row.version}>
                  {t('diff.label', { version: row.version })}
                </option>
              ))}
            </select>
            <span className="ms-auto">
              +{counts.added} {t('diff.change.added')} · −{counts.removed}{' '}
              {t('diff.change.removed')} · {counts.same} {t('diff.change.same')}
            </span>
          </div>
          <ul
            className="mt-2 max-h-56 overflow-y-auto rounded-lg bg-sunken p-2 ltr-island"
            dir="ltr"
          >
            {lines.map((line, index) => (
              <li
                key={`${index}-${line.kind}`}
                className={cn(
                  'whitespace-pre-wrap break-words px-1 font-mono text-micro',
                  line.kind === 'added' && 'bg-accent-soft text-accent-text',
                  line.kind === 'removed' && 'bg-danger-bg text-danger-fg',
                  line.kind === 'same' && 'text-fg-secondary',
                )}
              >
                {line.kind === 'added' ? '+ ' : line.kind === 'removed' ? '− ' : '  '}
                {line.text}
              </li>
            ))}
          </ul>
        </>
      )}
      {name && references !== null && (
        <div className="mt-3 border-t border-border-default pt-2">
          <h4 className="text-micro font-semibold uppercase tracking-wide text-fg-muted">
            {t('references.title')}
          </h4>
          {references.length === 0 ? (
            <p className="mt-1 text-caption text-fg-muted">{t('references.empty')}</p>
          ) : (
            <ul className="mt-1 flex flex-col gap-1">
              {references.map((row) => (
                <li key={row.name} className="flex items-center justify-between text-caption">
                  <span className="bidi-isolate" dir="auto">
                    references/{row.name}.md
                  </span>
                  <span className="text-micro text-fg-muted">
                    {t('references.bytes', { bytes: row.bytes })}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
