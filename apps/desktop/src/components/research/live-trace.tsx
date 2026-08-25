/**
 * Live structured execution trace — the main running view.
 *
 * Derives step cards from session.events / research.status.new_events /
 * research.stream chunks (event names like section.start, section.end, etc.).
 *
 * Detects dead/hung sidecar via heartbeat timeout and surfaces a controlled,
 * recoverable error + restart affordance.
 */

import {
  AlertTriangle,
  CheckCircle2,
  ListFilter,
  Loader2,
  PauseCircle,
  RefreshCw,
  Square,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import {
  researchGet,
  researchStatus,
  researchStop,
  researchStream,
  mapResearchError,
} from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import type { ResearchEvent, ResearchStatus } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';

const STALE_THRESHOLD_MS = 15_000;

const STATUS_LABELS: Record<ResearchStatus, string> = {
  IDLE: 'Idle',
  PLANNING: 'Planning',
  APPROVAL_PENDING: 'Awaiting approval',
  IN_PROGRESS: 'Running',
  PROOFREAD: 'Proofreading',
  COMPILING: 'Compiling report',
  COMPLETE: 'Complete',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
};

/** Safely extract a string value from an event payload. */
function eventStr(event: ResearchEvent, key: string, fallback = ''): string {
  const v = event[key];
  if (typeof v === 'string') return v;
  if (typeof v === 'number') return String(v);
  return fallback;
}

/** Safely extract a number value from an event payload. */
function eventNum(event: ResearchEvent, key: string, fallback = 0): number {
  const v = event[key];
  if (typeof v === 'number') return v;
  return fallback;
}

/** Derive a display card from a P1 event. */
function eventCard(event: ResearchEvent): {
  title: string;
  phase: string;
  status: 'running' | 'done' | 'failed';
  detail?: string;
} {
  const name = event.event;
  if (name === 'created')
    return {
      title: 'Session created',
      phase: 'setup',
      status: 'done',
      detail: eventStr(event, 'topic'),
    };
  if (name === 'discovery.start')
    return { title: 'Discovering data sources', phase: 'discover', status: 'running' };
  if (name === 'discovery.done')
    return {
      title: 'Discovery complete',
      phase: 'discover',
      status: 'done',
      detail: `${eventNum(event, 'datasets')} datasets, ${eventNum(event, 'files')} files`,
    };
  if (name === 'plan.start') return { title: 'Generating plan', phase: 'plan', status: 'running' };
  if (name === 'plan.done')
    return {
      title: 'Plan generated',
      phase: 'plan',
      status: 'done',
      detail: `${eventNum(event, 'sections')} sections, revision ${eventNum(event, 'revision', 1)}`,
    };
  if (name === 'plan.approved')
    return {
      title: 'Plan approved',
      phase: 'plan',
      status: 'done',
      detail: `Revision ${eventNum(event, 'revision', 1)}`,
    };
  if (name === 'plan.modified')
    return {
      title: 'Plan modified',
      phase: 'plan',
      status: 'done',
      detail: `Revision ${eventNum(event, 'revision', 1)}`,
    };
  if (name === 'section.start')
    return {
      title: `Section: ${eventStr(event, 'section')}`,
      phase: 'section',
      status: 'running',
    };
  if (name === 'section.end')
    return {
      title: `Section: ${eventStr(event, 'section')}`,
      phase: 'section',
      status: 'done',
      detail: eventStr(event, 'status'),
    };
  if (name === 'section.timeout')
    return {
      title: `Section timeout: ${eventStr(event, 'section')}`,
      phase: 'section',
      status: 'failed',
    };
  if (name === 'section.failed')
    return {
      title: `Section failed: ${eventStr(event, 'section')}`,
      phase: 'section',
      status: 'failed',
      detail: eventStr(event, 'reason'),
    };
  if (name === 'section.written')
    return {
      title: `Written: ${eventStr(event, 'section')}`,
      phase: 'section',
      status: 'done',
      detail: `${eventNum(event, 'chars')} chars`,
    };
  if (name === 'prep.failed')
    return {
      title: 'Prep failed',
      phase: 'prep',
      status: 'failed',
      detail: eventStr(event, 'reason'),
    };
  if (name === 'prep.limitation')
    return {
      title: 'Prep limitation',
      phase: 'prep',
      status: 'failed',
      detail: eventStr(event, 'detail'),
    };
  if (name === 'proofread.done')
    return {
      title: 'Proofread complete',
      phase: 'proofread',
      status: 'done',
      detail: `${eventNum(event, 'redactions')} redactions`,
    };
  if (name === 'report.compiled')
    return {
      title: 'Report compiled',
      phase: 'report',
      status: 'done',
      detail: `${eventNum(event, 'pages')} pages, ${eventNum(event, 'chars')} chars`,
    };
  if (name === 'published') return { title: 'Published', phase: 'publish', status: 'done' };
  if (name === 'cancelled') return { title: 'Cancelled', phase: 'lifecycle', status: 'failed' };
  if (name === 'failed')
    return {
      title: 'Failed',
      phase: 'lifecycle',
      status: 'failed',
      detail: eventStr(event, 'reason'),
    };
  if (name === 'status')
    return {
      title: `Status: ${eventStr(event, 'status')}`,
      phase: 'lifecycle',
      status: 'done',
    };
  return { title: name, phase: 'other', status: 'done' };
}

function ProgressBar({ progress, status }: { progress: number; status: ResearchStatus }) {
  const percent = Math.round(progress * 100);
  const isTerminal = status === 'COMPLETE' || status === 'FAILED' || status === 'CANCELLED';

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-micro text-fg-muted">
        <span>{STATUS_LABELS[status]}</span>
        <span>{percent}%</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-surface-2"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full rounded-full transition-all duration-standard motion-reduce:transition-none ${isTerminal && status !== 'COMPLETE' ? 'bg-danger-fg' : 'bg-accent'}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

export function EventRow({ event }: { event: ResearchEvent }) {
  const card = eventCard(event);
  const time = new Date(event.ts * 1000).toLocaleTimeString();
  const StatusIcon =
    card.status === 'done' ? CheckCircle2 : card.status === 'failed' ? XCircle : Loader2;
  const variant =
    card.status === 'done' ? 'success' : card.status === 'failed' ? 'danger' : 'accent';

  return (
    <div className="flex items-start gap-3 rounded-lg border border-border-default bg-surface p-3">
      <StatusIcon
        className={`size-4 shrink-0 mt-0.5 ${card.status === 'running' ? 'animate-spin motion-reduce:animate-none text-accent' : card.status === 'failed' ? 'text-danger-fg' : 'text-success-fg'}`}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-caption font-semibold">{card.title}</span>
          <Badge variant={variant}>{card.phase}</Badge>
        </div>
        {card.detail && <p className="mt-0.5 text-micro text-fg-muted">{card.detail}</p>}
      </div>
      <span className="shrink-0 text-micro text-fg-muted">{time}</span>
    </div>
  );
}

export function LiveTrace() {
  const { t } = useTranslation('research');
  const { client, reconnect } = useBridge();
  const {
    activeRecord,
    activeSummary,
    activeStream,
    setActiveRecord,
    setActiveSummary,
    upsertSession,
    setView,
    setTraceInspectorOpen,
    traceInspectorOpen,
    initStream,
    pushEvent,
    markStale,
  } = useResearchStore();

  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const sessionId = activeRecord?.session_id;
  const stream = activeStream();
  const status = activeRecord?.status ?? activeSummary?.status ?? 'IDLE';
  const progress = activeSummary?.progress ?? 0;
  const isRunning =
    status === 'IN_PROGRESS' ||
    status === 'PLANNING' ||
    status === 'COMPILING' ||
    status === 'PROOFREAD';
  const isComplete = status === 'COMPLETE';
  const isFailed = status === 'FAILED';
  const isCancelled = status === 'CANCELLED';
  const isStale = stream?.isStale ?? false;

  // Start streaming when session is running
  useEffect(() => {
    if (!sessionId || !isRunning) return;
    initStream(sessionId);
    const cursor = stream?.cursor ?? 0;
    const controller = new AbortController();

    researchStream(
      client,
      { session_id: sessionId, cursor, follow: true, timeout: 300 },
      (chunk) => {
        pushEvent(sessionId, chunk.event, chunk.cursor);
      },
      controller.signal,
    ).catch(() => {
      // Stream ended — poll for final status
    });

    // Also poll status periodically as a fallback
    pollTimer.current = setInterval(() => {
      researchStatus(client, { session_id: sessionId, cursor: stream?.cursor ?? 0 })
        .then((result) => {
          setActiveSummary(result);
          for (const evt of result.new_events) {
            pushEvent(sessionId, evt, result.cursor);
          }
          if (
            result.status === 'COMPLETE' ||
            result.status === 'FAILED' ||
            result.status === 'CANCELLED'
          ) {
            researchGet(client, sessionId)
              .then(setActiveRecord)
              .catch(() => {});
          }
        })
        .catch(() => {
          markStale(sessionId, true);
        });
    }, 3_000);

    return () => {
      controller.abort();
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [sessionId, isRunning]);

  // Heartbeat stale detection
  useEffect(() => {
    if (!sessionId || !isRunning) return;
    const timer = setInterval(() => {
      const currentStream = useResearchStore.getState().activeStream();
      if (!currentStream?.heartbeatAt) return;
      if (Date.now() - currentStream.heartbeatAt > STALE_THRESHOLD_MS) {
        markStale(sessionId, true);
      }
    }, 5_000);
    return () => clearInterval(timer);
  }, [sessionId, isRunning, markStale]);

  const handleStop = useCallback(() => {
    if (!sessionId || stopping) return;
    setStopping(true);
    setError(null);
    researchStop(client, sessionId)
      .then((summary) => {
        upsertSession(summary);
        setActiveSummary(summary);
        return researchGet(client, sessionId);
      })
      .then(setActiveRecord)
      .catch((err: unknown) => {
        const mapped = mapResearchError(err);
        setError(mapped.fallback);
      })
      .finally(() => setStopping(false));
  }, [sessionId, client, upsertSession, setActiveSummary, setActiveRecord, stopping]);

  const handleRestart = useCallback(() => {
    reconnect();
    setError(null);
  }, [reconnect]);

  if (!activeRecord && !activeSummary) {
    return (
      <div className="flex items-center justify-center p-8 text-body text-fg-muted">
        {t('noActiveSession')}
      </div>
    );
  }

  const events = stream?.events ?? activeRecord?.events ?? [];

  return (
    <div className="flex flex-col gap-4 overflow-y-auto">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setView('list')}
          className="text-caption text-fg-muted hover:text-fg-primary"
        >
          ← {t('backToList')}
        </button>
        <h3 className="min-w-0 flex-1 truncate text-body font-semibold">
          {activeRecord?.topic ?? activeSummary?.topic ?? ''}
        </h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setTraceInspectorOpen(!traceInspectorOpen)}
          aria-pressed={traceInspectorOpen}
        >
          <ListFilter aria-hidden />
          {t('trace')}
        </Button>
      </div>

      <ProgressBar progress={progress} status={status} />

      {isStale && (
        <div
          className="flex items-center gap-3 rounded-lg border border-warning-fg/50 bg-warning-bg p-3"
          role="alert"
        >
          <AlertTriangle className="size-5 shrink-0 text-warning-fg" aria-hidden />
          <div className="flex-1">
            <p className="text-caption font-semibold text-warning-fg">{t('trace.stale.title')}</p>
            <p className="text-micro text-warning-fg">{t('trace.stale.description')}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={handleRestart}>
            <RefreshCw aria-hidden />
            {t('trace.stale.restart')}
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="rounded-md bg-danger-bg p-2.5 text-caption text-danger-fg">
          {error}
        </p>
      )}

      {isComplete && (
        <div className="flex items-center gap-3 rounded-lg border border-success-fg/30 bg-success-bg p-3">
          <CheckCircle2 className="size-5 text-success-fg" aria-hidden />
          <p className="flex-1 text-caption text-success-fg">{t('trace.completed')}</p>
          <Button variant="primary" size="sm" onClick={() => setView('report')}>
            {t('trace.viewReport')}
          </Button>
        </div>
      )}

      {isFailed && (
        <div className="flex items-center gap-3 rounded-lg border border-danger-fg/30 bg-danger-bg p-3">
          <XCircle className="size-5 text-danger-fg" aria-hidden />
          <p className="flex-1 text-caption text-danger-fg">
            {activeRecord?.error ?? t('trace.failed')}
          </p>
        </div>
      )}

      {isCancelled && (
        <div className="flex items-center gap-3 rounded-lg border border-border-default bg-surface-2 p-3">
          <PauseCircle className="size-5 text-fg-muted" aria-hidden />
          <p className="flex-1 text-caption text-fg-muted">{t('trace.cancelled')}</p>
        </div>
      )}

      {isRunning && (
        <Button
          variant="primary"
          size="md"
          onClick={handleStop}
          disabled={stopping}
          aria-label={t('trace.stop')}
          className="bg-danger-fg text-white hover:bg-danger-fg/90 w-fit"
        >
          <Square aria-hidden />
          {stopping ? t('trace.stopping') : t('trace.stop')}
        </Button>
      )}

      <div className="flex flex-col gap-2" aria-live="polite" aria-relevant="additions">
        {events.length === 0 ? (
          <div
            className="flex items-center justify-center p-8 text-body text-fg-muted"
            role="status"
          >
            {isRunning ? t('trace.waitingForSteps') : t('trace.noSteps')}
          </div>
        ) : (
          events.map((event, i) => (
            <EventRow key={`${event.event}-${event.ts}-${i}`} event={event} />
          ))
        )}
      </div>
    </div>
  );
}
