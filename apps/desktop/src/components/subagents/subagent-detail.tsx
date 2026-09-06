/**
 * Detail view for one subagent: configuration, live counters, controls, log.
 *
 * The log is appended from the `subagent.logs` stream owned by the route, so
 * this component stays a pure rendering of what it is handed.
 */

import { Ban, Play, Pause } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { SubagentLogTail } from '@/components/subagents/subagent-log-tail';
import { ProgressBar, SubagentStatusBadge } from '@/components/subagents/status-badge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import type { BridgeLogEntry, BridgeSubagent } from '@/lib/bridge/types';
import { isTerminalStatus } from '@/lib/bridge/types';
import { formatClock, formatDuration, formatTokens } from '@/utils/format';

/** Where the `subagent.logs` stream stands for the child on screen. */
export type SubagentStreamPhase = 'connecting' | 'live' | 'ended' | 'disconnected';

/** A labelled counter in the metrics strip. */
function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-micro uppercase tracking-wide text-fg-muted">{label}</span>
      <span className="tabular text-body font-semibold">{value}</span>
      {hint && <span className="text-micro text-fg-muted">{hint}</span>}
    </div>
  );
}

interface SubagentDetailProps {
  agent: BridgeSubagent;
  /** Streamed log lines; falls back to the snapshot's replayed log. */
  log: BridgeLogEntry[];
  /** Log lines missing from the rendered tail (bounded retention). */
  logDropped?: number;
  /** Explicit stream state, rendered beside the activity log. */
  streamPhase?: SubagentStreamPhase;
  busy?: boolean;
  onCancel: () => void;
  onPause: () => void;
  onResume: () => void;
}

export function SubagentDetail({
  agent,
  log,
  logDropped = 0,
  streamPhase,
  busy = false,
  onCancel,
  onPause,
  onResume,
}: SubagentDetailProps) {
  const { t } = useTranslation('subagents');
  const terminal = isTerminalStatus(agent.status);
  const paused = agent.status === 'paused';

  // The Pause and Resume buttons swap in place. If the swap happens while the
  // control is focused, the old node unmounts and keyboard focus falls back
  // to <body>; restore it onto the replacement so a keyboard user can toggle
  // pause/resume without re-tabbing to the control.
  const pauseResumeRef = useRef<HTMLButtonElement | null>(null);
  const hadFocusRef = useRef(false);
  useEffect(() => {
    if (hadFocusRef.current) {
      hadFocusRef.current = false;
      pauseResumeRef.current?.focus();
    }
  }, [paused]);
  const markFocused = () => {
    hadFocusRef.current = document.activeElement === pauseResumeRef.current;
  };

  const streamLabel: Record<SubagentStreamPhase, string> = {
    connecting: t('streamConnecting'),
    live: t('streamLive'),
    ended: t('streamEnded'),
    disconnected: t('streamDisconnected'),
  };

  return (
    <section
      aria-label={t('detailLabel', { name: agent.name })}
      className="flex min-h-0 flex-col gap-4"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-h3 font-semibold">{agent.name}</h3>
            <SubagentStatusBadge status={agent.status} />
            {agent.pipeline_id && agent.pipeline_index !== null && (
              <Badge variant="accent">{t('stage', { number: agent.pipeline_index + 1 })}</Badge>
            )}
          </div>
          <p className="ltr-island text-micro text-fg-muted">{agent.subagent_id}</p>
        </div>

        <div className="flex shrink-0 gap-2">
          {paused ? (
            <Button
              ref={pauseResumeRef}
              size="sm"
              onClick={() => {
                markFocused();
                onResume();
              }}
              disabled={busy}
            >
              <Play aria-hidden />
              {t('resume')}
            </Button>
          ) : (
            <Button
              ref={pauseResumeRef}
              size="sm"
              onClick={() => {
                markFocused();
                onPause();
              }}
              disabled={busy || terminal}
            >
              <Pause aria-hidden />
              {t('pause')}
            </Button>
          )}
          <Button size="sm" variant="danger-outline" onClick={onCancel} disabled={busy || terminal}>
            <Ban aria-hidden />
            {t('cancel')}
          </Button>
        </div>
      </header>

      <div className="flex flex-col gap-1.5">
        <ProgressBar
          value={agent.progress}
          status={agent.status}
          label={t('progress', { name: agent.name })}
        />
        <p className="text-micro text-fg-muted">
          {t('limitProgress', { percent: Math.round(agent.progress * 100) })}
          {agent.limit_hit && ` — ${t('limitStopped', { limit: agent.limit_hit })}`}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 rounded-lg border border-border-default bg-surface p-3 sm:grid-cols-4">
        <Metric label={t('turns')} value={`${agent.turn_count} / ${agent.max_turns}`} />
        <Metric
          label={t('tokens')}
          value={`${formatTokens(agent.token_count)} / ${formatTokens(agent.max_tokens)}`}
        />
        <Metric
          label={t('elapsed')}
          value={formatDuration(agent.elapsed)}
          hint={t('durationLimit', { duration: formatDuration(agent.max_duration) })}
        />
        <Metric label={t('started')} value={formatClock(agent.started_at)} />
      </div>

      <dl className="grid gap-x-4 gap-y-2 text-caption sm:grid-cols-[auto_1fr]">
        <dt className="font-medium text-fg-secondary">{t('model')}</dt>
        <dd className="ltr-island">
          {agent.model_provider}
          {agent.model_name && ` · ${agent.model_name}`}
        </dd>

        <dt className="font-medium text-fg-secondary">{t('tools')}</dt>
        <dd className="flex flex-wrap gap-1">
          {agent.tools.length === 0 ? (
            <span className="text-fg-muted">{t('noTools')}</span>
          ) : (
            agent.tools.map((tool) => (
              <Badge key={tool} variant="neutral">
                {tool}
              </Badge>
            ))
          )}
        </dd>

        <dt className="font-medium text-fg-secondary">{t('task')}</dt>
        <dd className="selectable whitespace-pre-wrap">{agent.prompt}</dd>

        {agent.system_prompt && (
          <>
            <dt className="font-medium text-fg-secondary">{t('system')}</dt>
            <dd className="selectable whitespace-pre-wrap text-fg-secondary">
              {agent.system_prompt}
            </dd>
          </>
        )}

        {agent.context && (
          <>
            <dt className="font-medium text-fg-secondary">{t('inheritedContext')}</dt>
            <dd className="selectable whitespace-pre-wrap text-fg-secondary">{agent.context}</dd>
          </>
        )}
      </dl>

      {agent.result !== null && (
        <div className="flex flex-col gap-1">
          <h4 className="text-caption font-semibold text-fg-secondary">{t('result')}</h4>
          <p className="selectable whitespace-pre-wrap rounded-lg border border-success-fg/30 bg-success-bg p-3 text-body">
            {agent.result}
          </p>
        </div>
      )}

      {agent.error !== null && (
        <div className="flex flex-col gap-1">
          <h4 className="text-caption font-semibold text-fg-secondary">{t('error')}</h4>
          <p
            role="alert"
            className="rounded-lg border border-danger-fg/30 bg-danger-bg p-3 text-body text-danger-fg"
          >
            {agent.error}
          </p>
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-caption font-semibold text-fg-secondary">{t('activityLog')}</h4>
          {streamPhase && (
            <span
              role="status"
              className={
                streamPhase === 'disconnected'
                  ? 'text-micro text-warning-fg'
                  : 'text-micro text-fg-muted'
              }
            >
              {streamLabel[streamPhase]}
            </span>
          )}
        </div>
        {logDropped > 0 && (
          <p className="text-micro text-fg-muted">{t('logTruncated', { count: logDropped })}</p>
        )}
        <SubagentLogTail log={log} />
      </div>
    </section>
  );
}
