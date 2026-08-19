/**
 * Scheduler — recurring prompts, exposed at last (S06).
 *
 * The engine already exists in the sidecar (`dream/scheduler.py`,
 * `dream/cron.py`, `dream/nl_schedule.py`); this screen only surfaces it:
 * list, create from Persian/English prose (live `schedule.preview`), toggle,
 * run-now, history, delete — and the fail-closed approval queue for
 * dangerous scheduled runs.
 */

import {
  AlarmClock,
  Check,
  ChevronDown,
  ChevronUp,
  History,
  Play,
  Plus,
  ShieldAlert,
  Trash2,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ConfirmDialog } from '@/components/shared/confirm-dialog';
import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useBridge } from '@/lib/bridge/hooks';
import {
  approveScheduleRun,
  createSchedule,
  deleteSchedule,
  getSchedule,
  listApprovals,
  listSchedules,
  previewSchedule,
  runScheduleNow,
  toggleSchedule,
} from '@/lib/bridge/schedule';
import type {
  BridgeApproval,
  BridgeSchedule,
  BridgeScheduleRun,
  SchedulePreview,
} from '@/lib/bridge/types';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useTranslation } from '@/lib/i18n';
import { absoluteTime, jalaliDateTime, relativeTime } from '@/utils/time';

/** Approvals refresh cadence while any scheduled run is waiting on a human. */
const APPROVAL_POLL_MS = 4000;

export function SchedulerRoute() {
  const { t } = useTranslation('scheduler');
  const { client } = useBridge();

  const [schedules, setSchedules] = useState<BridgeSchedule[]>([]);
  const [approvals, setApprovals] = useState<BridgeApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleting, setDeleting] = useState<BridgeSchedule | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [runs, setRuns] = useState<BridgeScheduleRun[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [scheduleResult, approvalResult] = await Promise.all([
        listSchedules(client),
        listApprovals(client),
      ]);
      setSchedules(scheduleResult.schedules);
      setApprovals(
        approvalResult.approvals.filter((a) => !a.resolved && a.name === 'schedule.execute'),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'));
    }
  }, [client, t]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        await refresh();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  // While a scheduled run waits for a human, keep polling the queue; the
  // daemon denies it on its own timeout (fail-closed), the UI just follows.
  useEffect(() => {
    if (approvals.length === 0) return;
    const timer = setInterval(() => void refresh(), APPROVAL_POLL_MS);
    return () => clearInterval(timer);
  }, [approvals.length, refresh]);

  const onToggle = async (schedule: BridgeSchedule) => {
    setBusyId(schedule.id);
    try {
      await toggleSchedule(client, schedule.id, !schedule.enabled);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'));
    } finally {
      setBusyId(null);
    }
  };

  const onRunNow = async (schedule: BridgeSchedule) => {
    setBusyId(schedule.id);
    try {
      if (schedule.require_approval) {
        // The RPC blocks until a human answers the gate, so do not await it:
        // the approval queue below is where the decision happens.
        void runScheduleNow(client, schedule.id).catch(() => {});
        await refresh();
      } else {
        await runScheduleNow(client, schedule.id);
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'));
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async () => {
    if (!deleting) return;
    try {
      await deleteSchedule(client, deleting.id);
      setDeleting(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'));
    }
  };

  const onExpand = async (schedule: BridgeSchedule) => {
    if (expanded === schedule.id) {
      setExpanded(null);
      return;
    }
    try {
      const detail = await getSchedule(client, schedule.id);
      setRuns(detail.runs);
      setExpanded(schedule.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'));
    }
  };

  const onApproval = async (approval: BridgeApproval, allowed: boolean) => {
    try {
      await approveScheduleRun(client, approval.approval_id, allowed);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'));
    }
  };

  return (
    <section aria-label={t('title')} className="mx-auto w-full max-w-4xl p-6">
      <header className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-h2 font-semibold">{t('title')}</h2>
          <p className="text-body text-fg-secondary">{t('subtitle')}</p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" aria-hidden />
          {t('newSchedule')}
        </Button>
      </header>

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-md border border-border-default bg-surface p-3 text-caption text-fg-secondary"
        >
          {error}
        </p>
      )}

      {approvals.length > 0 && (
        <div className="mb-4 rounded-xl border border-border-default bg-surface p-4">
          <h3 className="mb-2 flex items-center gap-2 text-h3 font-semibold">
            <ShieldAlert className="size-4 text-accent-text" aria-hidden />
            {t('approvalsTitle')}
          </h3>
          <ul className="flex flex-col gap-2">
            {approvals.map((approval) => (
              <li key={approval.approval_id} className="flex items-center gap-3">
                <span className="min-w-0 flex-1 truncate text-caption" dir="auto">
                  {approval.summary}
                </span>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void onApproval(approval, true)}
                >
                  <Check className="size-4" aria-hidden />
                  {t('approve')}
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => void onApproval(approval, false)}
                >
                  <X className="size-4" aria-hidden />
                  {t('deny')}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!loading && schedules.length === 0 ? (
        <EmptyState
          icon={AlarmClock}
          title={t('noTasks')}
          description={t('noTasksDesc')}
          action={{ label: t('newSchedule'), onClick: () => setCreateOpen(true) }}
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {schedules.map((schedule) => (
            <li
              key={schedule.id}
              className="rounded-xl border border-border-default bg-surface p-4 shadow-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="me-auto text-h3 font-semibold">{schedule.name}</h3>
                {schedule.require_approval && (
                  <Badge variant="warning">
                    <ShieldAlert className="size-3" aria-hidden />
                    {t('approvalBadge')}
                  </Badge>
                )}
                {schedule.exhausted && <Badge variant="neutral">{t('exhaustedBadge')}</Badge>}
                {!schedule.enabled && !schedule.exhausted && (
                  <Badge variant="neutral">{t('disabledBadge')}</Badge>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  aria-label={`${schedule.enabled ? t('disable') : t('enable')}: ${schedule.name}`}
                  disabled={busyId === schedule.id || schedule.exhausted}
                  onClick={() => void onToggle(schedule)}
                >
                  {schedule.enabled ? t('stateOn') : t('stateOff')}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={busyId === schedule.id}
                  onClick={() => void onRunNow(schedule)}
                >
                  <Play className="size-3.5" aria-hidden />
                  {t('runNow')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-expanded={expanded === schedule.id}
                  onClick={() => void onExpand(schedule)}
                >
                  <History className="size-3.5" aria-hidden />
                  {t('history')}
                  {expanded === schedule.id ? (
                    <ChevronUp className="size-3.5" aria-hidden />
                  ) : (
                    <ChevronDown className="size-3.5" aria-hidden />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`${t('delete')}: ${schedule.name}`}
                  onClick={() => setDeleting(schedule)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </div>

              <p className="mt-1 text-body text-fg-secondary" dir="auto">
                {schedule.human}
              </p>
              <p className="ltr-island mt-0.5 font-mono text-micro text-fg-muted">
                {schedule.cron_expression}
              </p>
              <dl className="mt-2 grid gap-x-6 gap-y-1 text-caption sm:grid-cols-2">
                <div className="flex gap-2">
                  <dt className="text-fg-muted">{t('nextRun')}:</dt>
                  <dd>
                    {schedule.next_run ? (
                      <>
                        {absoluteTime(schedule.next_run)}
                        <span className="ms-2 text-fg-muted" dir="rtl">
                          {jalaliDateTime(schedule.next_run)}
                        </span>
                      </>
                    ) : (
                      '—'
                    )}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-fg-muted">{t('lastRun')}:</dt>
                  <dd>
                    {schedule.last_run ? relativeTime(schedule.last_run) : '—'}
                    <span className="ms-2 text-fg-muted">
                      {t('runsCount', { count: schedule.run_count })}
                    </span>
                  </dd>
                </div>
              </dl>

              {expanded === schedule.id && (
                <div className="mt-3 border-t border-border-default pt-2">
                  <p className="mb-1 text-micro font-semibold uppercase text-fg-muted">
                    {t('historyTitle')}
                  </p>
                  {runs.length === 0 ? (
                    <p className="text-caption text-fg-muted">{t('historyEmpty')}</p>
                  ) : (
                    <ul className="flex flex-col gap-1">
                      {runs.map((run) => (
                        <li key={run.id} className="flex items-center gap-2 text-caption">
                          <Badge
                            variant={
                              run.status === 'success'
                                ? 'success'
                                : run.status === 'running'
                                  ? 'info'
                                  : 'danger'
                            }
                          >
                            {t(runStatusKey(run.status))}
                          </Badge>
                          <span className="text-fg-muted">{absoluteTime(run.started_at)}</span>
                          <span className="min-w-0 flex-1 truncate" dir="auto">
                            {run.result_summary}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* The key remounts the dialog on every open/close, so its fields start
          blank each time without a reset effect. */}
      <CreateScheduleDialog
        key={createOpen ? 'open' : 'closed'}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => void refresh()}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t('confirmDeleteTitle')}
        description={t('confirmDeleteDesc')}
        confirmLabel={t('delete')}
        onConfirm={() => void onDelete()}
      />
    </section>
  );
}

/** i18n key for one history-row status. */
function runStatusKey(status: string): string {
  switch (status) {
    case 'success':
      return 'statusSuccess';
    case 'error':
      return 'statusError';
    case 'approval_denied':
      return 'statusDenied';
    default:
      return 'statusRunning';
  }
}

/** Create form with a live prose→cron preview and Jalali next-run. */
function CreateScheduleDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation('scheduler');
  const { client } = useBridge();

  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [rhythm, setRhythm] = useState('');
  const [requireApproval, setRequireApproval] = useState(false);
  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [busy, setBusy] = useState(false);

  const debouncedRhythm = useDebouncedValue(rhythm, 200);

  useEffect(() => {
    if (!open) return;
    const text = debouncedRhythm.trim();
    // An empty rhythm renders the "keep typing" hint from the state below;
    // a stale preview from a previous keystroke is ignored, never cleared
    // synchronously.
    if (!text) return;
    let cancelled = false;
    void previewSchedule(client, { natural_language: text })
      .then((result) => {
        if (!cancelled) setPreview(result);
      })
      .catch(() => {
        if (!cancelled) setPreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [client, debouncedRhythm, open]);

  const valid = Boolean(preview?.valid) && Boolean(name.trim()) && Boolean(prompt.trim());

  const submit = async () => {
    setBusy(true);
    try {
      await createSchedule(client, {
        name: name.trim(),
        prompt: prompt.trim(),
        natural_language: rhythm.trim(),
        require_approval: requireApproval,
      });
      onOpenChange(false);
      onCreated();
    } finally {
      setBusy(false);
    }
  };

  const jalali = useMemo(
    () => (preview?.valid && preview.next_run ? jalaliDateTime(preview.next_run) : null),
    [preview],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(34rem,92vw)]">
        <DialogHeader>
          <DialogTitle>{t('newSchedule')}</DialogTitle>
          <DialogDescription>{t('rhythmHelp')}</DialogDescription>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-caption font-medium">
            {t('nameLabel')}
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('namePlaceholder')}
              className="h-9 rounded-md border border-border-default bg-canvas px-3 text-body outline-none focus:border-accent"
            />
          </label>
          <label className="flex flex-col gap-1 text-caption font-medium">
            {t('promptLabel')}
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={t('promptPlaceholder')}
              rows={2}
              className="rounded-md border border-border-default bg-canvas px-3 py-2 text-body outline-none focus:border-accent"
            />
          </label>
          <label className="flex flex-col gap-1 text-caption font-medium">
            {t('rhythmLabel')}
            <input
              value={rhythm}
              onChange={(event) => setRhythm(event.target.value)}
              placeholder={t('rhythmPlaceholder')}
              dir="auto"
              className="h-9 rounded-md border border-border-default bg-canvas px-3 text-body outline-none focus:border-accent"
            />
          </label>

          <div aria-live="polite" className="rounded-md border border-border-default bg-canvas p-3">
            <p className="mb-1 text-micro font-semibold uppercase text-fg-muted">
              {t('previewTitle')}
            </p>
            {rhythm.trim() === '' ? (
              <p className="text-caption text-fg-muted">{t('previewEmpty')}</p>
            ) : preview === null ? (
              <p className="text-caption text-fg-muted">…</p>
            ) : preview.valid ? (
              <div className="flex flex-col gap-1 text-caption">
                <p dir="auto">{preview.human}</p>
                <p className="ltr-island font-mono text-micro text-fg-muted">
                  {t('previewCron')}: {preview.cron_expression}
                </p>
                {preview.next_run && (
                  <p>
                    {t('previewNext')}: {absoluteTime(preview.next_run)}
                  </p>
                )}
                {jalali && (
                  <p data-testid="preview-jalali" dir="rtl">
                    {t('previewJalali')}: {jalali}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-caption text-fg-muted">{t('previewInvalid')}</p>
            )}
          </div>

          <label className="flex items-start gap-2 text-caption">
            <input
              type="checkbox"
              checked={requireApproval}
              onChange={(event) => setRequireApproval(event.target.checked)}
              className="mt-0.5 size-4 accent-current"
            />
            <span>
              {t('approvalLabel')}
              <span className="block text-micro text-fg-muted">{t('approvalHelp')}</span>
            </span>
          </label>
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button variant="primary" disabled={!valid || busy} onClick={() => void submit()}>
            {t('create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
