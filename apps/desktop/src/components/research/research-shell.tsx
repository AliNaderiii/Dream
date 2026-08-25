/**
 * Research workbench shell (P2).
 *
 * Orchestrates the five views: list, composer, plan approval, live trace,
 * and report viewer. Manages the transition between them and provides the
 * trace inspector side panel.
 */

import { Plus } from 'lucide-react';
import { useEffect } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { researchList } from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import { useResearchStore } from '@/stores/research-store';

import { ResearchSessionList } from './research-session-list';
import { ResearchComposer } from './research-composer';
import { PlanPanel } from './plan-panel';
import { LiveTrace } from './live-trace';
import { ReportViewer } from './report-viewer';
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
      </header>

      <div className="flex min-h-0 flex-1 gap-4">
        <main className="flex min-w-0 flex-1 flex-col">
          {view === 'list' && <ResearchSessionList />}
          {view === 'composer' && <ResearchComposer />}
          {view === 'plan' && <PlanPanel />}
          {view === 'trace' && <LiveTrace />}
          {view === 'report' && <ReportViewer />}
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
