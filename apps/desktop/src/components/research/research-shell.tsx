/**
 * Research workbench shell (P2).
 *
 * Orchestrates research sessions, plans, traces, reports, and the
 * 3-Agent Dialectic Debate & Self-Reflective Mental Model Studio.
 */

import { BrainCircuit, ListOrdered, Plus } from 'lucide-react';
import { useEffect } from 'react';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import { researchList } from '@/lib/bridge/research';
import { useTranslation } from '@/lib/i18n';
import { useResearchStore } from '@/stores/research-store';

import { DialecticStudio } from './dialectic-studio';
import { LiveTrace } from './live-trace';
import { PlanPanel } from './plan-panel';
import { ReportViewer } from './report-viewer';
import { ResearchComposer } from './research-composer';
import { ResearchSessionList } from './research-session-list';
import { TraceInspector } from './trace-inspector';

export function ResearchShell() {
  const { t } = useTranslation('research');
  const { client } = useBridge();
  const { view, traceInspectorOpen, setSessions, setView } = useResearchStore();

  // Load sessions on mount
  useEffect(() => {
    let cancelled = false;
    researchList(client)
      .then((result) => {
        if (!cancelled) setSessions(result.sessions);
      })
      .catch(() => {
        // Echo mode or offline — sessions already seeded
      });
    return () => {
      cancelled = true;
    };
  }, [client, setSessions]);

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-h1 font-bold">{t('title')}</h2>
          <p className="text-body text-fg-secondary">{t('subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          {(view === 'list' || view === 'dialectic') && (
            <div className="flex rounded-md border border-border-default p-0.5">
              <Button
                variant={view === 'list' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setView('list')}
              >
                <ListOrdered className="mr-1 h-4 w-4" />
                Sessions
              </Button>
              <Button
                variant={view === 'dialectic' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setView('dialectic')}
              >
                <BrainCircuit className="mr-1 h-4 w-4" />
                Dialectic Studio
              </Button>
            </div>
          )}
          {view === 'list' && (
            <Button
              variant="primary"
              size="md"
              onClick={() => setView('composer')}
              aria-label={t('newResearch')}
            >
              <Plus aria-hidden />
              {t('newResearch')}
            </Button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 gap-4">
        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
          {view === 'list' && <ResearchSessionList />}
          {view === 'composer' && <ResearchComposer />}
          {view === 'plan' && <PlanPanel />}
          {view === 'trace' && <LiveTrace />}
          {view === 'report' && <ReportViewer />}
          {view === 'dialectic' && <DialecticStudio />}
        </main>

        {traceInspectorOpen && view === 'trace' && (
          <aside
            className="w-96 shrink-0 overflow-y-auto rounded-lg border border-border-default bg-surface p-4"
            aria-label={t('traceInspector')}
          >
            <TraceInspector />
          </aside>
        )}
      </div>
    </div>
  );
}
