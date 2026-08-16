/**
 * Detail view for one subagent: configuration, live counters, controls, log.
 *
 * The log is appended from the `subagent.logs` stream owned by the route, so
 * this component stays a pure rendering of what it is handed.
 */

import { Ban, Play, Pause } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { ProgressBar, SubagentStatusBadge } from '@/components/subagents/status-badge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { BridgeLogEntry, BridgeSubagent } from '@/lib/bridge/types';
import { isTerminalStatus } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';
import { formatClock, formatDuration, formatTokens } from '@/utils/format';

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

const LEVEL_CLASS: Record<string, string> = {
  error: 'text-danger-fg',
  warning: 'text-warning-fg',
  info: 'text-fg-secondary',
};

interface SubagentDetailProps {
  agent: BridgeSubagent;
  /** Streamed log lines; falls back to the snapshot's replayed log. */
  log: BridgeLogEntry[];
  busy?: boolean;
  onCancel: () => void;
  onPause: () => void;
  onResume: () => void;
}

export function SubagentDetail({
  agent,
  log,
  busy = false,
  onCancel,
  onPause,
  onResume,
}: SubagentDetailProps) {
  const logRef = useRef<HTMLOListElement>(null);
  const terminal = isTerminalStatus(agent.status);

  // Follow the tail as lines arrive.
  useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [log.length]);

  return (
    <section aria-label={`Subagent ${agent.name}`} className="flex min-h-0 flex-col gap-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-h3 font-semibold">{agent.name}</h3>
            <SubagentStatusBadge status={agent.status} />
            {agent.pipeline_id && agent.pipeline_index !== null && (
              <Badge variant="accent">Stage {agent.pipeline_index + 1}</Badge>
            )}
          </div>
          <p className="ltr-island text-micro text-fg-muted">{agent.subagent_id}</p>
        </div>

        <div className="flex shrink-0 gap-2">
          {agent.status === 'paused' ? (
            <Button size="sm" onClick={onResume} disabled={busy}>
              <Play aria-hidden />
              Resume
            </Button>
          ) : (
            <Button size="sm" onClick={onPause} disabled={busy || terminal}>
              <Pause aria-hidden />
              Pause
            </Button>
          )}
          <Button size="sm" variant="danger-outline" onClick={onCancel} disabled={busy || terminal}>
            <Ban aria-hidden />
            Cancel
          </Button>
        </div>
      </header>

      <div className="flex flex-col gap-1.5">
        <ProgressBar
          value={agent.progress}
          status={agent.status}
          label={`${agent.name} progress`}
        />
        <p className="text-micro text-fg-muted">
          {Math.round(agent.progress * 100)}% of the tightest limit
          {agent.limit_hit && ` — stopped on ${agent.limit_hit}`}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 rounded-lg border border-border-default bg-surface p-3 sm:grid-cols-4">
        <Metric label="Turns" value={`${agent.turn_count} / ${agent.max_turns}`} />
        <Metric
          label="Tokens"
          value={`${formatTokens(agent.token_count)} / ${formatTokens(agent.max_tokens)}`}
        />
        <Metric
          label="Elapsed"
          value={formatDuration(agent.elapsed)}
          hint={`limit ${formatDuration(agent.max_duration)}`}
        />
        <Metric label="Started" value={formatClock(agent.started_at)} />
      </div>

      <dl className="grid gap-x-4 gap-y-2 text-caption sm:grid-cols-[auto_1fr]">
        <dt className="font-medium text-fg-secondary">Model</dt>
        <dd className="ltr-island">
          {agent.model_provider}
          {agent.model_name && ` · ${agent.model_name}`}
        </dd>

        <dt className="font-medium text-fg-secondary">Tools</dt>
        <dd className="flex flex-wrap gap-1">
          {agent.tools.length === 0 ? (
            <span className="text-fg-muted">none granted</span>
          ) : (
            agent.tools.map((tool) => (
              <Badge key={tool} variant="neutral">
                {tool}
              </Badge>
            ))
          )}
        </dd>

        <dt className="font-medium text-fg-secondary">Task</dt>
        <dd className="selectable whitespace-pre-wrap">{agent.prompt}</dd>

        {agent.system_prompt && (
          <>
            <dt className="font-medium text-fg-secondary">System</dt>
            <dd className="selectable whitespace-pre-wrap text-fg-secondary">
              {agent.system_prompt}
            </dd>
          </>
        )}

        {agent.context && (
          <>
            <dt className="font-medium text-fg-secondary">Inherited context</dt>
            <dd className="selectable whitespace-pre-wrap text-fg-secondary">{agent.context}</dd>
          </>
        )}
      </dl>

      {agent.result !== null && (
        <div className="flex flex-col gap-1">
          <h4 className="text-caption font-semibold text-fg-secondary">Result</h4>
          <p className="selectable whitespace-pre-wrap rounded-lg border border-success-fg/30 bg-success-bg p-3 text-body">
            {agent.result}
          </p>
        </div>
      )}

      {agent.error !== null && (
        <div className="flex flex-col gap-1">
          <h4 className="text-caption font-semibold text-fg-secondary">Error</h4>
          <p
            role="alert"
            className="rounded-lg border border-danger-fg/30 bg-danger-bg p-3 text-body text-danger-fg"
          >
            {agent.error}
          </p>
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-1">
        <h4 className="text-caption font-semibold text-fg-secondary">Activity log</h4>
        <ol
          ref={logRef}
          aria-label="Activity log"
          className="ltr-island max-h-56 min-h-24 overflow-y-auto rounded-lg border border-border-default bg-sunken p-2 font-mono text-micro"
        >
          {log.length === 0 ? (
            <li className="p-2 text-fg-muted">Waiting for the first line…</li>
          ) : (
            log.map((entry, index) => (
              <li key={`${entry.ts}-${index}`} className="flex gap-2 px-1 py-0.5">
                <span className="tabular shrink-0 text-fg-muted">{formatClock(entry.ts)}</span>
                <span
                  className={cn(
                    'min-w-0 break-words',
                    LEVEL_CLASS[entry.level] ?? 'text-fg-primary',
                  )}
                >
                  {entry.message}
                </span>
              </li>
            ))
          )}
        </ol>
      </div>
    </section>
  );
}
