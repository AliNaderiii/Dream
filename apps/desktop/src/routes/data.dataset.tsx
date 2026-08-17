/**
 * Per-dataset workbench (P-09): Preview / Profile / Charts / Notebook /
 * Report tabs over one registered dataset. All heavy computation happens in
 * the sidecar's sandbox; this route only orchestrates RPCs and renders.
 */

import { ArrowLeft, BarChart3, BookOpen, FileText, Table2, Activity } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ChartGallery } from '@/components/data/chart-gallery';
import { DataTable } from '@/components/data/data-table';
import { NotebookView } from '@/components/data/notebook-view';
import { ProfilingCard } from '@/components/data/profiling-card';
import { ReportPreview } from '@/components/data/report-preview';
import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import {
  createChart,
  generateReport,
  getReportMarkdown,
  profileDataset,
  readNotebook,
  runNotebookCell,
  openJupyterLab,
  suggestCharts,
} from '@/lib/bridge/data-science';
import { useBridge } from '@/lib/bridge/hooks';
import type {
  ChartResultDto,
  ChartSpecDto,
  DatasetProfileDto,
  NotebookCellDto,
} from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

type Tab = 'preview' | 'profile' | 'charts' | 'notebook' | 'report';

const TABS: { id: Tab; label: string; icon: typeof Table2 }[] = [
  { id: 'preview', label: 'Preview', icon: Table2 },
  { id: 'profile', label: 'Profile', icon: Activity },
  { id: 'charts', label: 'Charts', icon: BarChart3 },
  { id: 'notebook', label: 'Notebook', icon: BookOpen },
  { id: 'report', label: 'Report', icon: FileText },
];

interface DatasetDetail {
  dataset_id: string;
  name: string;
  filename: string;
  format: string;
  shape: [number, number];
  columns: string[];
  cleaned: boolean;
  preview?: Record<string, unknown>[];
}

export function DataDatasetRoute() {
  const { datasetId = '' } = useParams();
  const { client } = useBridge();
  const [tab, setTab] = useState<Tab>('preview');
  const [detail, setDetail] = useState<DatasetDetail | null>(null);
  const [profile, setProfile] = useState<DatasetProfileDto | null>(null);
  const [charts, setCharts] = useState<ChartResultDto[]>([]);
  const [suggestions, setSuggestions] = useState<ChartSpecDto[]>([]);
  const [notebookPath, setNotebookPath] = useState<string | null>(null);
  const [cells, setCells] = useState<NotebookCellDto[]>([]);
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [pdfPath, setPdfPath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fail = (err: unknown) => setError(err instanceof Error ? err.message : String(err));

  // Base data: the registry record (with preview rows when available).
  useEffect(() => {
    let cancelled = false;
    void client
      .call<DatasetDetail>('data.get_dataset', { dataset_id: datasetId })
      .then((record) => {
        if (!cancelled) setDetail(record);
      })
      .catch(fail);
    return () => {
      cancelled = true;
    };
  }, [client, datasetId]);

  // Lazy per-tab loading — profile/report/notebook only when opened.
  useEffect(() => {
    let cancelled = false;
    if (tab === 'profile' && !profile) {
      void profileDataset(client, datasetId)
        .then((result) => {
          if (!cancelled) setProfile(result);
        })
        .catch(fail);
    }
    if (tab === 'charts' && suggestions.length === 0) {
      void suggestCharts(client, datasetId)
        .then((result) => {
          if (!cancelled) setSuggestions(result.charts);
        })
        .catch(fail);
    }
    if (tab === 'report' && reportMarkdown === null) {
      void getReportMarkdown(client, datasetId)
        .then((result) => {
          if (!cancelled && result.markdown) {
            setReportMarkdown(result.markdown);
            setPdfPath(`${datasetId}/report.pdf`);
          }
        })
        .catch(() => undefined /* no report yet is not an error */);
    }
    return () => {
      cancelled = true;
    };
  }, [tab, client, datasetId, profile, suggestions.length, reportMarkdown]);

  const renderChart = useCallback(
    async (spec: ChartSpecDto) => {
      setBusy(true);
      setError(null);
      try {
        const result = await createChart(client, { ...spec, dataset_id: datasetId });
        setCharts((existing) => [...existing, result]);
      } catch (err) {
        fail(err);
      } finally {
        setBusy(false);
      }
    },
    [client, datasetId],
  );

  const makeReport = useCallback(async () => {
    if (!detail) return;
    setBusy(true);
    setError(null);
    try {
      const result = await generateReport(client, datasetId, `${detail.name} — Report`);
      setPdfPath(result.pdf_path);
      const markdown = await getReportMarkdown(client, datasetId);
      setReportMarkdown(markdown.markdown);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }, [client, datasetId, detail]);

  const loadNotebook = useCallback(
    async (path: string) => {
      const document = await readNotebook(client, path);
      setNotebookPath(document.notebook_path);
      setCells(document.cells);
    },
    [client],
  );

  // The echo transport seeds one notebook per demo dataset; try to find it.
  useEffect(() => {
    if (tab !== 'notebook' || notebookPath) return;
    let cancelled = false;
    const load = async () => {
      const document = await readNotebook(client, `${datasetId}/notebooks/exploration.ipynb`);
      if (cancelled) return;
      setNotebookPath(document.notebook_path);
      setCells(document.cells);
    };
    load().catch(() => {
      /* no notebook yet — the empty state handles it */
    });
    return () => {
      cancelled = true;
    };
  }, [tab, datasetId, notebookPath, client]);

  const runCell = useCallback(
    async (index: number) => {
      if (!notebookPath) return;
      setBusy(true);
      try {
        await runNotebookCell(client, notebookPath, index);
        await loadNotebook(notebookPath);
      } catch (err) {
        fail(err);
      } finally {
        setBusy(false);
      }
    },
    [client, notebookPath, loadNotebook],
  );

  const openLab = useCallback(() => {
    if (!notebookPath) return;
    void openJupyterLab(client, notebookPath)
      .then(({ url }) => window.open(url, '_blank', 'noopener'))
      .catch(fail);
  }, [client, notebookPath]);

  const previewRows = useMemo(() => detail?.preview ?? [], [detail]);

  if (!detail) {
    return (
      <div className="p-4">
        {error ? (
          <EmptyState icon={Table2} title="Dataset not found" description={error} />
        ) : (
          <p className="text-body text-fg-muted">Loading dataset…</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <Link
          to="/data"
          aria-label="Back to datasets"
          className="flex size-8 items-center justify-center rounded-md text-fg-secondary hover:bg-surface-2"
        >
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
        </Link>
        <div className="min-w-0 flex-1">
          <h2 className="flex items-center gap-2 text-h2 font-bold">
            <span className="truncate">{detail.name}</span>
            <Badge variant="neutral">{detail.format}</Badge>
            {detail.cleaned && <Badge variant="success">cleaned</Badge>}
          </h2>
          <p className="text-caption text-fg-muted">
            {detail.shape[0].toLocaleString()} rows × {detail.shape[1]} columns · {detail.filename}
          </p>
        </div>
      </header>

      <nav
        role="tablist"
        aria-label="Workbench sections"
        className="flex gap-1 border-b border-border-default"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              'flex items-center gap-1.5 border-b-2 px-3 py-2 text-body transition-colors duration-fast',
              tab === id
                ? 'border-accent font-medium text-accent-text'
                : 'border-transparent text-fg-secondary hover:text-fg-primary',
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </button>
        ))}
      </nav>

      {error && (
        <p role="alert" className="rounded-md bg-danger-bg p-2.5 text-caption text-danger-fg">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto" role="tabpanel">
        {tab === 'preview' &&
          (previewRows.length > 0 ? (
            <DataTable columns={detail.columns} rows={previewRows} />
          ) : (
            <EmptyState
              icon={Table2}
              title="No preview rows"
              description="The sidecar returns up to 50 preview rows per dataset."
            />
          ))}
        {tab === 'profile' &&
          (profile ? (
            <ProfilingCard profile={profile} />
          ) : (
            <p className="text-body text-fg-muted">Profiling…</p>
          ))}
        {tab === 'charts' && (
          <ChartGallery
            charts={charts}
            suggestions={suggestions}
            onRender={(spec) => void renderChart(spec)}
            rendering={busy}
          />
        )}
        {tab === 'notebook' && (
          <NotebookView
            notebookPath={notebookPath}
            cells={cells}
            onRunCell={(index) => void runCell(index)}
            onOpenLab={openLab}
            running={busy}
          />
        )}
        {tab === 'report' && (
          <ReportPreview
            markdown={reportMarkdown}
            pdfPath={pdfPath}
            onGenerate={() => void makeReport()}
            generating={busy}
          />
        )}
      </div>
    </div>
  );
}
