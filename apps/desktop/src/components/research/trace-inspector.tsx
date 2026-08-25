/**
 * Trace inspector side panel — shows every tool call with args (collapsed),
 * result excerpt, error, and risk tier. Filterable by phase/tool/status.
 */

import { AlertTriangle, Filter, Shield, ShieldAlert, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import type { ResearchToolCall, RiskTier } from '@/lib/bridge/research-types';
import { redactSecrets } from '@/lib/bridge/research';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

const RISK_STYLES: Record<RiskTier, string> = {
  safe: 'text-success-fg',
  caution: 'text-warning-fg',
  danger: 'text-danger-fg',
};

const RISK_ICONS: Record<RiskTier, typeof Shield> = {
  safe: Shield,
  caution: ShieldAlert,
  danger: AlertTriangle,
};

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

function ToolCallRow({ call }: { call: ResearchToolCall }) {
  const { t } = useTranslation('research');
  const RiskIcon = RISK_ICONS[call.risk_tier];
  const resultPreview = call.result
    ? redactSecrets(call.result).slice(0, 80) + (call.result.length > 80 ? '…' : '')
    : call.error
      ? redactSecrets(call.error).slice(0, 80)
      : '';

  return (
    <div className="flex flex-col gap-1 rounded-md border border-border-default bg-surface px-2.5 py-2">
      <div className="flex items-center gap-2">
        <RiskIcon className={cn('size-3.5 shrink-0', RISK_STYLES[call.risk_tier])} aria-hidden />
        <span className="font-mono text-micro font-semibold">{call.tool_name}</span>
        {call.error ? (
          <Badge variant="danger">{t('trace.error')}</Badge>
        ) : call.completed_at ? (
          <Badge variant="success">{t('trace.ok')}</Badge>
        ) : (
          <Badge variant="accent">{t('trace.running')}</Badge>
        )}
      </div>
      {resultPreview && <p className="text-micro text-fg-muted">{resultPreview}</p>}
      <div className="flex flex-wrap gap-x-2 text-micro text-fg-muted">
        <span>
          {t('trace.args')}: {Object.keys(call.args).length} keys
        </span>
      </div>
    </div>
  );
}

export function TraceInspector() {
  const { t } = useTranslation('research');
  const { activeStream, traceFilter, setTraceFilter, setTraceInspectorOpen } = useResearchStore();

  const stream = activeStream();

  // Collect all tool calls from steps
  const allToolCalls: { call: ResearchToolCall; phase: string; stepStatus: string }[] = [];
  if (stream) {
    for (const step of stream.steps) {
      if (step.tool_calls) {
        for (const call of step.tool_calls) {
          allToolCalls.push({ call, phase: step.phase, stepStatus: step.status });
        }
      }
    }
  }

  // Apply filters
  const filteredCalls = allToolCalls.filter(({ call, phase, stepStatus }) => {
    if (traceFilter.phase && phase !== traceFilter.phase) return false;
    if (traceFilter.status && stepStatus !== traceFilter.status) return false;
    if (traceFilter.tool && call.tool_name !== traceFilter.tool) return false;
    return true;
  });

  // Unique tool names for the filter
  const uniqueTools = [...new Set(allToolCalls.map((c) => c.call.tool_name))].sort();

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-caption font-semibold">
          <Filter className="size-4" aria-hidden />
          {t('traceInspector')}
        </h3>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setTraceInspectorOpen(false)}
          aria-label={t('close')}
        >
          <X aria-hidden />
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-2">
        <div className="flex gap-2">
          <select
            value={traceFilter.phase ?? ''}
            onChange={(e) => setTraceFilter({ phase: e.target.value || null })}
            className="h-7 flex-1 rounded border border-border-default bg-surface px-2 text-micro outline-none focus:border-accent"
            aria-label={t('trace.filterByPhase')}
          >
            <option value="">{t('trace.allPhases')}</option>
            {ALL_PHASES.map((phase) => (
              <option key={phase} value={phase}>
                {phase}
              </option>
            ))}
          </select>
          <select
            value={traceFilter.tool ?? ''}
            onChange={(e) => setTraceFilter({ tool: e.target.value || null })}
            className="h-7 flex-1 rounded border border-border-default bg-surface px-2 text-micro outline-none focus:border-accent"
            aria-label={t('trace.filterByTool')}
          >
            <option value="">{t('trace.allTools')}</option>
            {uniqueTools.map((tool) => (
              <option key={tool} value={tool}>
                {tool}
              </option>
            ))}
          </select>
        </div>
        {(traceFilter.phase || traceFilter.tool || traceFilter.status) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setTraceFilter({ phase: null, status: null, tool: null })}
          >
            <X aria-hidden />
            {t('trace.clearFilters')}
          </Button>
        )}
      </div>

      {/* Stats */}
      <div className="flex gap-3 text-micro text-fg-muted">
        <span>{t('trace.totalCalls', { count: filteredCalls.length })}</span>
        <span>·</span>
        <span className="text-danger-fg">
          {t('trace.errors', {
            count: filteredCalls.filter((c) => c.call.error).length,
          })}
        </span>
      </div>

      {/* Tool call list */}
      <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto" role="list">
        {filteredCalls.length === 0 ? (
          <p className="p-4 text-center text-micro text-fg-muted">
            {allToolCalls.length === 0 ? t('trace.noToolCalls') : t('trace.noMatches')}
          </p>
        ) : (
          filteredCalls.map(({ call }) => <ToolCallRow key={call.call_id} call={call} />)
        )}
      </div>
    </div>
  );
}
