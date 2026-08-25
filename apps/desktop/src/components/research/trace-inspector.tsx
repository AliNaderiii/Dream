/**
 * Trace inspector side panel — shows every event with details.
 * Filterable by event name.
 */

import { Filter, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { redactSecrets } from '@/lib/bridge/research';
import { useResearchStore } from '@/stores/research-store';

const PHASE_COLORS: Record<string, string> = {
  setup: 'bg-blue-500',
  discover: 'bg-teal-500',
  plan: 'bg-violet-500',
  section: 'bg-green-500',
  prep: 'bg-amber-500',
  proofread: 'bg-pink-500',
  report: 'bg-indigo-500',
  publish: 'bg-emerald-500',
  lifecycle: 'bg-gray-500',
  other: 'bg-gray-400',
};

export function TraceInspector() {
  const { t } = useTranslation('research');
  const { activeRecord, activeStream, traceFilter, setTraceFilter, setTraceInspectorOpen } =
    useResearchStore();

  const stream = activeStream();
  const allEvents = stream?.events ?? activeRecord?.events ?? [];

  // Apply filter
  const filteredEvents = traceFilter.event
    ? allEvents.filter((e) => e.event === traceFilter.event)
    : allEvents;

  // Unique event names for the filter
  const uniqueEvents = [...new Set(allEvents.map((e) => e.event))].sort();

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

      {/* Filter */}
      <div className="flex flex-col gap-2">
        <select
          value={traceFilter.event ?? ''}
          onChange={(e) => setTraceFilter({ event: e.target.value || null })}
          className="h-7 rounded border border-border-default bg-surface px-2 text-micro outline-none focus:border-accent"
          aria-label={t('trace.filterByEvent')}
        >
          <option value="">{t('trace.allEvents')}</option>
          {uniqueEvents.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        {traceFilter.event && (
          <Button variant="ghost" size="sm" onClick={() => setTraceFilter({ event: null })}>
            <X aria-hidden />
            {t('trace.clearFilters')}
          </Button>
        )}
      </div>

      {/* Stats */}
      <div className="flex gap-3 text-micro text-fg-muted">
        <span>{t('trace.totalEvents', { count: filteredEvents.length })}</span>
      </div>

      {/* Event list */}
      <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto" role="list">
        {filteredEvents.length === 0 ? (
          <p className="p-4 text-center text-micro text-fg-muted">
            {allEvents.length === 0 ? t('trace.noEvents') : t('trace.noMatches')}
          </p>
        ) : (
          filteredEvents.map((event, i) => {
            const phase = event.event.split('.')[0] ?? 'other';
            const color = PHASE_COLORS[phase] ?? PHASE_COLORS.other;
            const details = Object.entries(event)
              .filter(([k]) => k !== 'event' && k !== 'ts')
              .map(
                ([k, v]) => `${k}: ${typeof v === 'string' ? redactSecrets(v) : JSON.stringify(v)}`,
              )
              .join(', ');
            const time = new Date(event.ts * 1000).toLocaleTimeString();

            return (
              <div
                key={`${event.event}-${event.ts}-${i}`}
                className="flex flex-col gap-0.5 rounded-md border border-border-default bg-surface px-2.5 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className={`size-2 rounded-full ${color}`} aria-hidden />
                  <span className="font-mono text-micro font-semibold">{event.event}</span>
                  <span className="ms-auto text-micro text-fg-muted">{time}</span>
                </div>
                {details && <p className="text-micro text-fg-muted">{details}</p>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
