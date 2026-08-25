/**
 * Step card — a collapsible, labeled card for each step in the execution
 * trace. Shows phase icon, status, live output, elapsed time, token/cost
 * badge, and a "Fix & retry" affordance for blocked/failed steps.
 */

import {
  AlertTriangle,
  Braces,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Code2,
  Eye,
  FileSearch,
  Lightbulb,
  Loader2,
  Map,
  PauseCircle,
  PlayCircle,
  Search,
  Shield,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import type {
  ResearchStep,
  ResearchToolCall,
  RiskTier,
  StepPhase,
  StepStatus,
} from '@/lib/bridge/research-types';
import { redactSecrets } from '@/lib/bridge/research';
import { truncateOutput } from '@/stores/research-store';
import { cn } from '@/utils/cn';

const PHASE_ICONS: Record<
  StepPhase,
  ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
> = {
  analyze: Search,
  plan: Map,
  discover: FileSearch,
  code: Code2,
  execute: PlayCircle,
  observe: Eye,
  evidence: Lightbulb,
  section: Braces,
};

const PHASE_COLORS: Record<StepPhase, string> = {
  analyze: 'text-blue-500',
  plan: 'text-violet-500',
  discover: 'text-teal-500',
  code: 'text-amber-500',
  execute: 'text-green-500',
  observe: 'text-orange-500',
  evidence: 'text-pink-500',
  section: 'text-indigo-500',
};

const STATUS_ICONS: Record<
  StepStatus,
  ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
> = {
  pending: Clock,
  running: Loader2,
  done: CheckCircle2,
  failed: XCircle,
  blocked: PauseCircle,
};

const STATUS_VARIANTS: Record<StepStatus, 'neutral' | 'accent' | 'success' | 'warning' | 'danger'> =
  {
    pending: 'neutral',
    running: 'accent',
    done: 'success',
    failed: 'danger',
    blocked: 'warning',
  };

const RISK_ICONS: Record<
  RiskTier,
  ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
> = {
  safe: Shield,
  caution: ShieldAlert,
  danger: AlertTriangle,
};

function formatElapsed(ms?: number): string {
  if (ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

function ToolCallBadge({ call }: { call: ResearchToolCall }) {
  const { t } = useTranslation('research');
  const [expanded, setExpanded] = useState(false);
  const RiskIcon = RISK_ICONS[call.risk_tier];

  return (
    <div className="rounded border border-border-default bg-surface-2 p-2 text-micro">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-start"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <RiskIcon
          className={cn(
            'size-3.5 shrink-0',
            call.risk_tier === 'safe' && 'text-success-fg',
            call.risk_tier === 'caution' && 'text-warning-fg',
            call.risk_tier === 'danger' && 'text-danger-fg',
          )}
          aria-hidden
        />
        <span className="font-mono font-semibold">{call.tool_name}</span>
        {call.error ? (
          <Badge variant="danger">{t('trace.error')}</Badge>
        ) : call.completed_at ? (
          <Badge variant="success">{t('trace.ok')}</Badge>
        ) : (
          <Badge variant="accent">{t('trace.running')}</Badge>
        )}
        <span className="ms-auto text-fg-muted">
          {expanded ? (
            <ChevronDown className="size-3" aria-hidden />
          ) : (
            <ChevronRight className="size-3" aria-hidden />
          )}
        </span>
      </button>
      {expanded && (
        <div className="mt-2 flex flex-col gap-1.5 ps-5">
          <div>
            <span className="text-fg-muted">{t('trace.args')}:</span>
            <pre className="mt-0.5 overflow-x-auto rounded bg-surface px-2 py-1 font-mono text-micro">
              {redactSecrets(JSON.stringify(call.args, null, 2))}
            </pre>
          </div>
          {call.result && (
            <div>
              <span className="text-fg-muted">{t('trace.result')}:</span>
              <p className="mt-0.5 text-micro">{redactSecrets(call.result)}</p>
            </div>
          )}
          {call.error && (
            <div>
              <span className="text-danger-fg">{t('trace.error')}:</span>
              <p className="mt-0.5 text-micro text-danger-fg">{redactSecrets(call.error)}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function StepCard({ step }: { step: ResearchStep }) {
  const { t } = useTranslation('research');
  const [expanded, setExpanded] = useState(step.status === 'running' || step.status === 'blocked');
  const PhaseIcon = PHASE_ICONS[step.phase];
  const StatusIcon = STATUS_ICONS[step.status];

  const output = step.output ? truncateOutput(redactSecrets(step.output), 20) : null;
  const hasToolCalls = step.tool_calls && step.tool_calls.length > 0;

  return (
    <div
      className={cn(
        'rounded-lg border bg-surface transition-colors motion-reduce:transition-none',
        step.status === 'running' && 'border-accent',
        step.status === 'done' && 'border-border-default',
        step.status === 'failed' && 'border-danger-fg/50',
        step.status === 'blocked' && 'border-warning-fg/50',
        step.status === 'pending' && 'border-border-default opacity-60',
      )}
      role="article"
      aria-label={step.title}
    >
      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center gap-3 p-3 text-start"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <PhaseIcon className={cn('size-5 shrink-0', PHASE_COLORS[step.phase])} aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-caption font-semibold">{step.title}</span>
            <Badge variant={STATUS_VARIANTS[step.status]}>
              <StatusIcon
                className={cn(
                  'size-3',
                  step.status === 'running' && 'animate-spin motion-reduce:animate-none',
                )}
                aria-hidden
              />
              {t(`stepStatus.${step.status}`)}
            </Badge>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-micro text-fg-muted">
            <span className="capitalize">{step.phase}</span>
            {step.elapsed_ms !== undefined && <span>{formatElapsed(step.elapsed_ms)}</span>}
            {step.tokens_used !== undefined && (
              <span>{(step.tokens_used / 1000).toFixed(1)}k tokens</span>
            )}
            {step.cost_usd !== undefined && step.cost_usd > 0 && (
              <span>${step.cost_usd.toFixed(3)}</span>
            )}
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="size-4 shrink-0 text-fg-muted" aria-hidden />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-fg-muted" aria-hidden />
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="flex flex-col gap-2 border-t border-border-default px-3 pb-3 pt-2">
          {/* Output */}
          {output && (
            <div>
              <span className="text-micro font-semibold text-fg-muted">{t('trace.output')}:</span>
              <pre className="mt-1 overflow-x-auto rounded bg-surface-2 px-3 py-2 font-mono text-micro leading-relaxed whitespace-pre-wrap">
                {output}
              </pre>
            </div>
          )}

          {/* Error */}
          {step.error && (
            <div className="rounded-md bg-danger-bg px-3 py-2">
              <p className="text-micro text-danger-fg">
                <strong>{t('trace.why')}:</strong> {redactSecrets(step.error)}
              </p>
              {step.status === 'blocked' && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  aria-label={t('trace.fixAndRetry')}
                >
                  {t('trace.fixAndRetry')}
                </Button>
              )}
            </div>
          )}

          {/* Tool calls */}
          {hasToolCalls && (
            <div className="flex flex-col gap-1.5">
              <span className="text-micro font-semibold text-fg-muted">
                {t('trace.toolCalls')} ({step.tool_calls!.length})
              </span>
              {step.tool_calls!.map((call) => (
                <ToolCallBadge key={call.call_id} call={call} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
