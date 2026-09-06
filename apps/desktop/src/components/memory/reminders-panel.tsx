/**
 * Reminder authoring panel (P-13) — the memory page's third tab.
 *
 * A reminder is a schedule of `kind: 'reminder'`: created, edited, paused,
 * resumed, run and deleted through the same `schedule.*` RPCs the scheduler
 * page uses, and fired by the same single daemon. No second engine. The
 * authoring surface adds only two things:
 *
 * - a **one-off** mode, where a date + time compiles to `M H D Mon *` cron
 *   with `max_runs: 1` (fires once, then finishes);
 * - reminder-shaped wording, states and empty/offline handling.
 *
 * Nothing about a reminder is written into URL state, and errors surface the
 * RPC message only.
 */

import {
  AlarmClock,
  BellRing,
  Check,
  ChevronDown,
  ChevronUp,
  History,
  Pencil,
  Play,
  Plus,
  Trash2,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ScheduleHistory } from '@/components/scheduler/schedule-history';
import { BridgeOfflineBanner } from '@/components/shared/bridge-offline-banner';
import { ConfirmDialog } from '@/components/shared/confirm-dialog';
import { EmptyState } from '@/components/shared/empty-state';
import { VirtualList } from '@/components/shared/virtual-list';
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
import type { RequestOptions } from '@/lib/bridge/client';
import { useBridge } from '@/lib/bridge/hooks';
import {
  createSchedule,
  deleteSchedule,
  getSchedule,
  listSchedulesOfKind,
  previewSchedule,
  runScheduleNow,
  toggleSchedule,
  updateSchedule,
} from '@/lib/bridge/schedule';
import type { BridgeSchedule, BridgeScheduleRun, SchedulePreview } from '@/lib/bridge/types';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { i18n, useTranslation } from '@/lib/i18n';
import { upcomingRuns } from '@/lib/schedule/cron';
import { absoluteTime, jalaliDateTime, relativeTime } from '@/utils/time';

import {
  EMPTY_REMINDER_DRAFT,
  isOneOff,
  oneOffCron,
  oneOffParts,
  reminderPrompt,
  validateOneOff,
  validateReminderText,
  type ReminderDraft,
} from './reminder-model';

/** The compiled cron the current draft would submit, or null when invalid. */
function draftCron(
  draft: ReminderDraft,
  preview: { key: string; result: SchedulePreview } | null,
): string | null {
  if (draft.mode === 'once') {
    if (validateOneOff(draft.date, draft.time, new Date()) !== null) return null;
    try {
      return oneOffCron(draft.date, draft.time);
    } catch {
      return null;
    }
  }
  const rhythm = draft.rhythm.trim();
  // Only a preview that answers *this* phrase counts — a stale response for
  // an earlier keystroke must never enable the submit button.
  if (!rhythm || preview === null || preview.key !== rhythm) return null;
  return preview.result.valid ? (preview.result.cron_expression ?? null) : null;
}

export function RemindersPanel() {
  const { t } = useTranslation('memory');
  const { client } = useBridge();

  const [reminders, setReminders] = useState<BridgeSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<BridgeSchedule | null>(null);
  const [deleting, setDeleting] = useState<BridgeSchedule | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [runs, setRuns] = useState<BridgeScheduleRun[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(
    async (options?: RequestOptions) => {
      setError(null);
      try {
        const result = await listSchedulesOfKind(client, 'reminder', true, options);
        setReminders(result.schedules);
      } catch (err) {
        if (!options?.signal?.aborted) {
          setError(err instanceof Error ? err.message : t('reminders.failedLoad'));
        }
      }
    },
    [client, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        await refresh({ signal: controller.signal });
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [refresh]);

  const onToggle = async (reminder: BridgeSchedule) => {
    if (busyId === reminder.id) return;
    setBusyId(reminder.id);
    try {
      await toggleSchedule(client, reminder.id, !reminder.enabled);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('reminders.failedSave'));
    } finally {
      setBusyId(null);
    }
  };

  const onRunNow = async (reminder: BridgeSchedule) => {
    if (busyId === reminder.id) return;
    setBusyId(reminder.id);
    try {
      await runScheduleNow(client, reminder.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('reminders.failedRun'));
    } finally {
      setBusyId(null);
    }
  };

  const onExpand = async (reminder: BridgeSchedule) => {
    if (expanded === reminder.id) {
      setExpanded(null);
      return;
    }
    try {
      const detail = await getSchedule(client, reminder.id);
      setRuns(detail.runs ?? []);
      setExpanded(reminder.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('reminders.failedLoad'));
    }
  };

  const onDelete = async () => {
    if (!deleting) return;
    try {
      await deleteSchedule(client, deleting.id);
      setDeleting(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('reminders.failedDelete'));
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-caption text-fg-secondary">{t('reminders.subtitle')}</p>
        <Button variant="primary" size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-4" aria-hidden />
          {t('reminders.new')}
        </Button>
      </div>

      <p aria-live="polite" className="sr-only">
        {loading ? t('reminders.loading') : t('reminders.shown', { count: reminders.length })}
      </p>

      <BridgeOfflineBanner />

      {error && (
        <div
          role="alert"
          className="mb-3 flex items-center gap-3 rounded-md border border-border-default bg-surface p-3 text-caption text-fg-secondary"
        >
          <span className="min-w-0 flex-1">{error}</span>
          <Button size="sm" variant="secondary" onClick={() => void refresh()}>
            {t('retry')}
          </Button>
        </div>
      )}

      {loading ? (
        <div role="status" aria-label={t('reminders.loading')} className="flex flex-col gap-2">
          {Array.from({ length: 3 }, (_, index) => (
            <div
              key={index}
              className="h-24 animate-pulse rounded-xl bg-surface-2 motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : reminders.length === 0 ? (
        <EmptyState
          icon={AlarmClock}
          title={t('reminders.empty')}
          description={t('reminders.emptyDesc')}
          action={{ label: t('reminders.new'), onClick: () => setCreating(true) }}
        />
      ) : (
        <VirtualList
          items={reminders}
          getKey={(reminder) => reminder.id}
          estimateSize={116}
          virtualizeAt={0}
          ariaLabel={t('reminders.listLabel')}
          className="min-h-0 flex-1"
          renderItem={(reminder) => {
            const once = isOneOff(reminder.max_runs, reminder.cron_expression);
            return (
              <div className="h-full pb-2">
                <article className="flex h-full flex-col rounded-xl border border-border-default bg-surface p-3 shadow-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="me-auto min-w-0 text-h3 font-semibold" dir="auto">
                      {reminder.name}
                    </h3>
                    {once && <Badge variant="info">{t('reminders.onceBadge')}</Badge>}
                    {reminder.exhausted && (
                      <Badge variant="success">{t('reminders.doneBadge')}</Badge>
                    )}
                    {!reminder.enabled && !reminder.exhausted && (
                      <Badge variant="neutral">{t('reminders.pausedBadge')}</Badge>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      aria-label={`${reminder.enabled ? t('reminders.pause') : t('reminders.resume')}: ${reminder.name}`}
                      disabled={busyId === reminder.id || reminder.exhausted}
                      onClick={() => void onToggle(reminder)}
                    >
                      {reminder.enabled ? t('reminders.pause') : t('reminders.resume')}
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busyId === reminder.id}
                      onClick={() => void onRunNow(reminder)}
                    >
                      <Play className="size-3.5" aria-hidden />
                      {t('reminders.runNow')}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-expanded={expanded === reminder.id}
                      onClick={() => void onExpand(reminder)}
                    >
                      <History className="size-3.5" aria-hidden />
                      {t('reminders.history')}
                      {expanded === reminder.id ? (
                        <ChevronUp className="size-3.5" aria-hidden />
                      ) : (
                        <ChevronDown className="size-3.5" aria-hidden />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`${t('reminders.edit')}: ${reminder.name}`}
                      onClick={() => setEditing(reminder)}
                    >
                      <Pencil className="size-4" aria-hidden />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`${t('reminders.delete')}: ${reminder.name}`}
                      onClick={() => setDeleting(reminder)}
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </Button>
                  </div>
                  <p className="mt-1 text-caption text-fg-secondary" dir="auto">
                    {reminder.human}
                  </p>
                  <p className="ltr-island mt-0.5 font-mono text-micro text-fg-muted">
                    {reminder.cron_expression}
                  </p>
                  <dl className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-caption">
                    <div className="flex gap-2">
                      <dt className="text-fg-muted">{t('reminders.nextFire')}:</dt>
                      <dd>
                        {reminder.next_run ? (
                          <>
                            {absoluteTime(reminder.next_run)}
                            <span
                              className="ms-2 text-fg-muted"
                              dir="rtl"
                              data-testid="reminder-next-jalali"
                            >
                              {jalaliDateTime(reminder.next_run)}
                            </span>
                          </>
                        ) : (
                          '—'
                        )}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-fg-muted">{t('reminders.lastFire')}:</dt>
                      <dd>
                        {reminder.last_run ? relativeTime(reminder.last_run) : '—'}
                        <span className="ms-2 text-fg-muted">
                          {t('reminders.firesCount', { count: reminder.run_count })}
                        </span>
                      </dd>
                    </div>
                  </dl>
                  {expanded === reminder.id && (
                    <div className="mt-2 border-t border-border-default pt-2">
                      <p className="mb-1 text-micro font-semibold uppercase text-fg-muted">
                        {t('reminders.historyTitle')}
                      </p>
                      <ScheduleHistory runs={runs} />
                    </div>
                  )}
                </article>
              </div>
            );
          }}
        />
      )}

      {/* The key remounts the dialog each open, so fields start fresh. */}
      <ReminderDialog
        key={creating ? 'create-open' : 'create-closed'}
        open={creating}
        reminder={null}
        onOpenChange={setCreating}
        onSaved={() => void refresh()}
      />
      <ReminderDialog
        key={editing ? `edit-${editing.id}` : 'edit-closed'}
        open={editing !== null}
        reminder={editing}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
        onSaved={() => void refresh()}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t('reminders.confirmDeleteTitle')}
        description={t('reminders.confirmDeleteDesc')}
        confirmLabel={t('reminders.delete')}
        onConfirm={() => void onDelete()}
      />
    </div>
  );
}

/** Prefill a draft from a stored reminder (create passes null → blanks). */
function draftFrom(reminder: BridgeSchedule | null): ReminderDraft {
  if (!reminder) return { ...EMPTY_REMINDER_DRAFT };
  const once = isOneOff(reminder.max_runs, reminder.cron_expression);
  const parts = once ? oneOffParts(reminder.cron_expression) : null;
  return {
    text: reminder.name,
    mode: once ? 'once' : 'repeat',
    date: parts?.date ?? '',
    time: parts?.time ?? '',
    rhythm: reminder.natural_language || reminder.cron_expression,
  };
}

/** Create/edit dialog: one-off date+time or a repeating rhythm, previewed live. */
function ReminderDialog({
  open,
  reminder,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  reminder: BridgeSchedule | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation('memory');
  const { t: tc } = useTranslation('common');
  const { client } = useBridge();

  const [draft, setDraft] = useState<ReminderDraft>(() => draftFrom(reminder));
  const [preview, setPreview] = useState<{ key: string; result: SchedulePreview } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debouncedRhythm = useDebouncedValue(draft.rhythm, 200);
  const debouncedDate = useDebouncedValue(draft.date, 150);
  const debouncedTime = useDebouncedValue(draft.time, 150);

  const textProblem =
    draft.text.trim().length === 0
      ? 'reminders.textRequired'
      : validateReminderText(draft.text)
        ? null
        : 'reminders.textTooLong';
  const oneOffProblem =
    draft.mode === 'once' ? validateOneOff(draft.date, draft.time, new Date()) : null;

  // Live preview. Repeat phrases go through `schedule.preview` exactly like
  // the scheduler page; one-off cron is compiled locally and then previewed
  // by the same call, so the verdict shown is always the server's. State is
  // only written from the promise callbacks — never synchronously in the
  // effect — and each result is keyed to the exact input it answers, so a
  // stale or superseded response cannot enable a submit.
  useEffect(() => {
    if (!open) return;
    let request: { natural_language?: string; cron_expression?: string };
    let key: string;
    if (draft.mode === 'once') {
      if (validateOneOff(debouncedDate, debouncedTime, new Date()) !== null) return;
      try {
        const cron = oneOffCron(debouncedDate, debouncedTime);
        request = { cron_expression: cron };
        key = cron;
      } catch {
        return;
      }
    } else {
      const text = debouncedRhythm.trim();
      if (!text) return;
      request = { natural_language: text };
      key = text;
    }
    const controller = new AbortController();
    void previewSchedule(client, request, { signal: controller.signal })
      .then((result) => setPreview({ key, result }))
      .catch(() => {
        if (!controller.signal.aborted) setPreview(null);
      });
    return () => controller.abort();
  }, [client, open, draft.mode, debouncedRhythm, debouncedDate, debouncedTime]);

  const cron = draftCron(draft, preview);
  const valid = cron !== null && textProblem === null;

  const nextRuns = useMemo(() => {
    if (!cron) return [];
    try {
      return upcomingRuns(cron, 3);
    } catch {
      return [];
    }
  }, [cron]);

  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const text = draft.text.trim();
      const prompt = reminderPrompt(text, i18n.language);
      if (reminder) {
        await updateSchedule(client, reminder.id, {
          name: text,
          prompt,
          ...(draft.mode === 'once'
            ? {
                cron_expression: oneOffCron(draft.date, draft.time),
                max_runs: 1,
              }
            : {
                natural_language: draft.rhythm.trim(),
                // Explicit null clears a one-off cap: once → repeat.
                max_runs: null,
              }),
        });
      } else {
        await createSchedule(client, {
          name: text,
          prompt,
          kind: 'reminder',
          ...(draft.mode === 'once'
            ? {
                cron_expression: oneOffCron(draft.date, draft.time),
                max_runs: 1,
              }
            : { natural_language: draft.rhythm.trim() }),
        });
      }
      onOpenChange(false);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('reminders.failedSave'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(34rem,92vw)]">
        <DialogHeader>
          <DialogTitle>{reminder ? t('reminders.edit') : t('reminders.new')}</DialogTitle>
          <DialogDescription>{t('reminders.help')}</DialogDescription>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-caption font-medium">
            {t('reminders.textLabel')}
            <textarea
              value={draft.text}
              onChange={(event) => setDraft((prev) => ({ ...prev, text: event.target.value }))}
              placeholder={t('reminders.textPlaceholder')}
              rows={2}
              dir="auto"
              aria-invalid={textProblem !== null}
              className="rounded-md border border-border-default bg-canvas px-3 py-2 text-body outline-none focus:border-accent"
            />
            {textProblem && <span className="text-micro text-danger-fg">{t(textProblem)}</span>}
          </label>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-caption font-medium">{t('reminders.modeLabel')}</legend>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-caption">
                <input
                  type="radio"
                  name={`reminder-mode-${reminder ? reminder.id : 'new'}`}
                  checked={draft.mode === 'once'}
                  onChange={() => setDraft((prev) => ({ ...prev, mode: 'once' }))}
                  className="size-4 accent-current"
                />
                {t('reminders.modeOnce')}
              </label>
              <label className="flex items-center gap-2 text-caption">
                <input
                  type="radio"
                  name={`reminder-mode-${reminder ? reminder.id : 'new'}`}
                  checked={draft.mode === 'repeat'}
                  onChange={() => setDraft((prev) => ({ ...prev, mode: 'repeat' }))}
                  className="size-4 accent-current"
                />
                {t('reminders.modeRepeat')}
              </label>
            </div>
          </fieldset>

          {draft.mode === 'once' ? (
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-caption font-medium">
                {t('reminders.dateLabel')}
                <input
                  type="date"
                  value={draft.date}
                  onChange={(event) => setDraft((prev) => ({ ...prev, date: event.target.value }))}
                  aria-invalid={oneOffProblem !== null}
                  className="h-9 rounded-md border border-border-default bg-canvas px-3 text-body outline-none focus:border-accent"
                />
              </label>
              <label className="flex flex-col gap-1 text-caption font-medium">
                {t('reminders.timeLabel')}
                <input
                  type="time"
                  value={draft.time}
                  onChange={(event) => setDraft((prev) => ({ ...prev, time: event.target.value }))}
                  aria-invalid={oneOffProblem !== null}
                  className="h-9 rounded-md border border-border-default bg-canvas px-3 text-body outline-none focus:border-accent"
                />
              </label>
              {oneOffProblem && (
                <p className="col-span-2 text-micro text-danger-fg">
                  {t(`reminders.${oneOffProblem}`)}
                </p>
              )}
            </div>
          ) : (
            <label className="flex flex-col gap-1 text-caption font-medium">
              {t('reminders.rhythmLabel')}
              <input
                value={draft.rhythm}
                onChange={(event) => setDraft((prev) => ({ ...prev, rhythm: event.target.value }))}
                placeholder={t('reminders.rhythmPlaceholder')}
                dir="auto"
                className="h-9 rounded-md border border-border-default bg-canvas px-3 text-body outline-none focus:border-accent"
              />
            </label>
          )}

          <div aria-live="polite" className="rounded-md border border-border-default bg-canvas p-3">
            <p className="mb-1 flex items-center gap-1 text-micro font-semibold uppercase text-fg-muted">
              <BellRing className="size-3" aria-hidden />
              {t('reminders.previewTitle')}
            </p>
            {!valid ? (
              <p className="text-caption text-fg-muted">
                {draft.mode === 'once'
                  ? oneOffProblem
                    ? t(`reminders.${oneOffProblem}`)
                    : t('reminders.previewInvalid')
                  : draft.rhythm.trim() === ''
                    ? t('reminders.previewEmpty')
                    : t('reminders.previewInvalid')}
              </p>
            ) : (
              <div className="flex flex-col gap-1 text-caption">
                <p dir="auto">
                  {draft.mode === 'once'
                    ? t('reminders.previewOnce')
                    : (preview?.result.human ?? cron)}
                </p>
                <p className="ltr-island font-mono text-micro text-fg-muted">
                  {t('reminders.previewCron')}: {cron}
                </p>
                {nextRuns.length > 0 && (
                  <ol aria-label={t('reminders.previewRuns')} className="flex flex-col gap-1">
                    {nextRuns.slice(0, draft.mode === 'once' ? 1 : 3).map((run) => {
                      const timestamp = run.getTime() / 1000;
                      return (
                        <li key={run.getTime()} className="grid gap-x-2 sm:grid-cols-2">
                          <span>
                            {t('reminders.previewNext')}: {absoluteTime(timestamp)}
                          </span>
                          <span data-testid="reminder-jalali" dir="rtl">
                            {t('reminders.previewJalali')}: {jalaliDateTime(timestamp)}
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </div>
            )}
          </div>

          {error && (
            <p role="alert" className="text-caption text-danger-fg">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            {tc('generic.cancel')}
          </Button>
          <Button variant="primary" disabled={!valid || busy} onClick={() => void submit()}>
            <Check className="size-4" aria-hidden />
            {busy ? tc('generic.saving') : reminder ? t('reminders.save') : t('reminders.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
