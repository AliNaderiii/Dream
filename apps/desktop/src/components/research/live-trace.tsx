/**
 * Live structured execution trace — the main running view.
 *
 * Renders the streaming progress as collapsible, labeled step cards with an
 * overall progress bar, ETA, and a prominent Stop button that truly cancels
 * (calls research.stop, reflects real server state).
 *
 * Detects dead/hung sidecar via heartbeat timeout and surfaces a controlled,
 * recoverable error + restart affordance.
 */

import { AlertTriangle, ListFilter, Pause, Play, RefreshCw, Square } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { researchStop, researchTrace, mapResearchError } from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import type { ResearchStep } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';

import { StepCard } from './step-card';

/** Heartbeat stale threshold — 15 seconds without a heartbeat. */
const STALE_THRESHOLD_MS = 15_000;

/** All possible phases in display order. */
const ALL_PHASES = [
  'analyze',
  'plan',
  'discover',
  'code',
  'execute',
  'observe',
  'evidence',
  'section',
] as const;

function ProgressBar({ completed, total }: { completed: number; total: number }) {
  const { t } = useTranslation('research');
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  const etaSeconds = total > 0 ? Math.max(0, (total - completed) * 12) : 0;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-micro text-fg-muted">
        <span>{t('trace.progress', { completed, total })}</span>
        <span>{percent}%</span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-surface-2"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t('trace.progressBar')}
      >
        <div
          className="h-full rounded-full bg-accent transition-all duration-standard motion-reduce:transition-none"
          style={{ width: `${percent}%` }}
        />
      </div>
      {etaSeconds > 0 && (
        <span className="text-micro text-fg-muted">
          {t('trace.eta', { minutes: Math.ceil(etaSeconds / 60) })}
        </span>
      )}
    </div>
  );
}

function TimelineBar({ steps }: { steps: ResearchStep[] }) {
  const phaseGroups = useMemo(() => {
    const groups = new Map<string, { total: number; done: number }>();
    for (const step of steps) {
      const group = groups.get(step.phase) ?? { total: 0, done: 0 };
      group.total += 1;
      if (step.status === 'done') group.done += 1;
      groups.set(step.phase, group);
    }
    return groups;
  }, [steps]);

  return (
    <div className="flex gap-1" role="list" aria-label="Section timeline">
      {ALL_PHASES.map((phase) => {
        const group = phaseGroups.get(phase);
        if (!group) {
          return (
            <div
              key={phase}
              className="h-1.5 flex-1 rounded-full bg-surface-2"
              role="listitem"
              title={phase}
            />
          );
        }
        const percent = group.total > 0 ? (group.done / group.total) * 100 : 0;
        return (
          <div
            key={phase}
            className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2"
            role="listitem"
            title={`${phase}: ${group.done}/${group.total}`}
          >
            <div
              className="absolute inset-y-0 start-0 rounded-full bg-accent"
              style={{ width: `${percent}%` }}
            />
          </div>
        );
      })}
    </div>
  );
}

export function LiveTrace() {
  const { t } = useTranslation('research');
  const { client, reconnect } = useBridge();
  const {
    activeSession,
    activeStream,
    upsertSession,
    setView,
    setTraceInspectorOpen,
    traceInspectorOpen,
  } = useResearchStore();
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const session = activeSession();
  const stream = activeStream();

  // Load trace steps from the store or echo
  useEffect(() => {
    if (!session) return;
    researchTrace(client, session.session_id)
      .then((result) => {
        const store = useResearchStore.getState();
        store.updateSteps(session.session_id, result.steps);
      })
      .catch(() => {
        // Echo or offline — steps may already be loaded
      });
  }, [session, client]);

  // Heartbeat stale detection
  useEffect(() => {
    if (!session || session.status !== 'running') return;

    heartbeatTimer.current = setInterval(() => {
      const currentStream = useResearchStore.getState().activeStream();
      if (!currentStream?.heartbeatAt) return;
      const elapsed = Date.now() - currentStream.heartbeatAt;
      if (elapsed > STALE_THRESHOLD_MS) {
        useResearchStore.getState().markStale(session.session_id, true);
      }
    }, 5_000);

    return () => {
      if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
    };
  }, [session]);

  const handleStop = useCallback(async () => {
    if (!session || stopping) return;
    setStopping(true);
    setError(null);
    try {
      const updated = await researchStop(client, session.session_id);
      upsertSession(updated);
    } catch (err) {
      const mapped = mapResearchError(err);
      setError(mapped.fallback);
    } finally {
      setStopping(false);
    }
  }, [session, client, upsertSession, stopping]);

  const handleViewReport = useCallback(() => {
    setView('report');
  }, [setView]);

  const handleRestart = useCallback(() => {
    reconnect();
    setError(null);
  }, [reconnect]);

  if (!session) {
    return (
      <div className="flex items-center justify-center p-8 text-body text-fg-muted">
        {t('noActiveSession')}
      </div>
    );
  }

  const steps = stream?.steps ?? [];
  const completedSteps = steps.filter((s) => s.status === 'done').length;
  const totalSteps = steps.length;
  const isRunning = session.status === 'running' || session.status === 'planning';
  const isCompleted = session.status === 'completed';
  const isFailed = session.status === 'failed';
  const isCancelled = session.status === 'cancelled';
  const isStale = stream?.isStale ?? false;

  return (
    <div className="flex flex-col gap-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setView('list')}
          className="text-caption text-fg-muted hover:text-fg-primary"
        >
          ← {t('backToList')}
        </button>
        <h3 className="min-w-0 flex-1 truncate text-body font-semibold">{session.topic}</h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setTraceInspectorOpen(!traceInspectorOpen)}
          aria-label={t('traceInspector')}
          aria-pressed={traceInspectorOpen}
        >
          <ListFilter aria-hidden />
          {t('trace')}
        </Button>
      </div>

      {/* Progress */}
      {totalSteps > 0 && (
        <div className="flex flex-col gap-2">
          <ProgressBar completed={completedSteps} total={totalSteps} />
          <TimelineBar steps={steps} />
        </div>
      )}

      {/* Status messages */}
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

      {isCompleted && (
        <div className="flex items-center gap-3 rounded-lg border border-success-fg/30 bg-success-bg p-3">
          <Play className="size-5 text-success-fg" aria-hidden />
          <p className="flex-1 text-caption text-success-fg">{t('trace.completed')}</p>
          <Button variant="primary" size="sm" onClick={handleViewReport}>
            {t('trace.viewReport')}
          </Button>
        </div>
      )}

      {isFailed && (
        <div className="flex items-center gap-3 rounded-lg border border-danger-fg/30 bg-danger-bg p-3">
          <AlertTriangle className="size-5 text-danger-fg" aria-hidden />
          <p className="flex-1 text-caption text-danger-fg">{session.error ?? t('trace.failed')}</p>
        </div>
      )}

      {isCancelled && (
        <div className="flex items-center gap-3 rounded-lg border border-border-default bg-surface-2 p-3">
          <Pause className="size-5 text-fg-muted" aria-hidden />
          <p className="flex-1 text-caption text-fg-muted">{t('trace.cancelled')}</p>
        </div>
      )}

      {/* Stop button */}
      {isRunning && (
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            size="md"
            onClick={() => void handleStop()}
            disabled={stopping}
            aria-label={t('trace.stop')}
            className="bg-danger-fg text-white hover:bg-danger-fg/90"
          >
            <Square aria-hidden />
            {stopping ? t('trace.stopping') : t('trace.stop')}
          </Button>
        </div>
      )}

      {/* Steps */}
      <div className="flex flex-col gap-2" aria-live="polite" aria-relevant="additions">
        {steps.length === 0 ? (
          <div
            className="flex items-center justify-center p-8 text-body text-fg-muted"
            role="status"
          >
            {isRunning ? t('trace.waitingForSteps') : t('trace.noSteps')}
          </div>
        ) : (
          steps.map((step) => <StepCard key={step.step_id} step={step} />)
        )}
      </div>
    </div>
  );
}
